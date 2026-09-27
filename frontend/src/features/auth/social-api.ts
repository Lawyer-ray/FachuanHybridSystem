/**
 * 社交登录 API。
 *
 * 后端约定（见 backend/apps/social_auth）：
 * - GET    /api/v1/social/providers                    列出已启用的登录方式（未登录可访问）
 * - POST   /api/v1/social/{provider}/session           生成授权 URL（内嵌二维码用）
 * - POST   /api/v1/social/token-exchange               用 TempAuth 码换 JWT
 * - GET    /api/v1/social/bindings                     当前用户已绑定的社交账号
 * - GET    /api/v1/social/provider-catalog             全部已知 Provider（含未启用）
 * - POST   /api/v1/social/{provider}/bind-session      发起绑定授权（需登录）
 * - DELETE /api/v1/social/{provider}/bind              解绑（需登录）
 *
 * 同源约定：授权会话的 state 存在 Django session cookie 里，而 SameSite=Lax 的
 * cookie 不会随跨域 XHR 发送。因此这里一律用**以 / 开头的同源路径**，让请求经
 * Vite 代理（见 vite.config.ts）与后端同源；若直连后端 origin，回调时 Django
 * 读不到 state 会判 invalid_session。
 *
 * 前导斜杠不能省：ky 按「当前文档目录」解析相对路径，`api/v1/...` 在
 * `/login`（单段）下恰好落到 `/api/v1/...`，但在 `/settings/bindings` 下会变成
 * `/settings/api/v1/...`，被 SPA fallback 返回 index.html，报 JSON 解析失败。
 */
import ky, { type KyInstance } from 'ky'
import { getAccessToken } from '@/lib/token'

/** 未登录即可用的客户端：不带 JWT，但要带 cookie（state 在 session 里）。 */
const socialClient: KyInstance = ky.create({
  credentials: 'same-origin',
  retry: 0,
})

/** 已登录才可用的客户端：同上，额外带 JWT。 */
const authedSocialClient: KyInstance = ky.create({
  credentials: 'same-origin',
  retry: 0,
  hooks: {
    beforeRequest: [
      ({ request }) => {
        const token = getAccessToken()
        if (token) request.headers.set('Authorization', `Bearer ${token}`)
      },
    ],
  },
})

export interface SocialProviderInfo {
  name: string
  display_name: string
  /** redirect：跳转到授权页；embedded_qr：前端渲染二维码 */
  login_mode: 'redirect' | 'embedded_qr'
  /** 渲染所需公开信息（app_id / authorize_url / 二维码尺寸），不含密钥。
   *  provider-catalog 里为 null 表示该平台尚未配置启用。 */
  client_config: {
    app_id?: string
    authorize_url?: string
    scope?: string
    width?: string
    height?: string
    [k: string]: string | undefined
  } | null
}

export interface SocialSession {
  /** 拼上 tmp_code 后即可完成跳转的授权页地址 */
  goto: string
  state: string
  expires_in: number
  /** 后端在「该方式不可用」时返回 200 + success:false，需在封装内转成异常 */
  success?: boolean
  message?: string
}

export interface SocialTokenExchangeResponse {
  success: boolean
  access: string
  refresh: string
  user_id?: number
  username?: string
  message?: string
}

export interface BoundAccount {
  provider: string
  display_name: string
  avatar_url: string
  bound_at: string
}

/** 生成授权 URL 的通用封装：业务失败是 200 + success:false，必须在这里 throw。 */
async function requestSession(client: KyInstance, path: string): Promise<SocialSession> {
  const data = await client.post(path).json<SocialSession>()
  if (data.success === false) {
    throw new Error(data.message || '该登录方式暂不可用')
  }
  return data
}

export const socialAuthApi = {
  async listProviders(): Promise<SocialProviderInfo[]> {
    try {
      const data = await socialClient.get('/api/v1/social/providers').json<{ providers: SocialProviderInfo[] }>()
      return data.providers ?? []
    } catch {
      // 拉不到登录方式不应阻塞账密登录，静默降级
      return []
    }
  },

  /** 生成授权 URL（内嵌二维码用）。未配置该登录方式时后端返回 200 + success:false。 */
  async createSession(provider: string): Promise<SocialSession> {
    // 不带尾斜杠：后端 ApiTrailingSlashMiddleware 会剥掉 /api/ 的尾斜杠
    return requestSession(socialClient, `/api/v1/social/${provider}/session`)
  },

  /**
   * 用回调页拿到的一次性码换 JWT。
   * 业务错误是 HTTP 200 + { success: false, message }，需在此 throw 让上层处理。
   */
  async exchangeToken(code: string): Promise<SocialTokenExchangeResponse> {
    return socialClient.post('/api/v1/social/token-exchange', { json: { code } }).json<SocialTokenExchangeResponse>()
  },
}

export const socialBindingsApi = {
  /** 当前用户已绑定的社交账号。 */
  async list(): Promise<BoundAccount[]> {
    const data = await authedSocialClient.get('/api/v1/social/bindings').json<{ accounts: BoundAccount[] }>()
    return data.accounts ?? []
  },

  /** 全部已知 Provider：client_config 为 null 表示平台未启用，前端显示灰态。 */
  async catalog(): Promise<SocialProviderInfo[]> {
    const data = await authedSocialClient
      .get('/api/v1/social/provider-catalog')
      .json<{ providers: SocialProviderInfo[] }>()
    return data.providers ?? []
  },

  /** 发起绑定授权。授权完成后后端把身份关联到当前登录用户，不新建律师账号。 */
  async createBindSession(provider: string, redirect = '/settings/bindings'): Promise<SocialSession> {
    return requestSession(
      authedSocialClient,
      `/api/v1/social/${provider}/bind-session?redirect=${encodeURIComponent(redirect)}`,
    )
  },

  /** 解绑。未绑定该平台时后端返回 success:false。 */
  async unbind(provider: string): Promise<{ success: boolean; message?: string }> {
    return authedSocialClient.delete(`/api/v1/social/${provider}/bind`).json()
  },
}
