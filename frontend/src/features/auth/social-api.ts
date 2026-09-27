/**
 * 社交登录 API。
 *
 * 后端约定（见 backend/apps/social_auth）：
 * - GET  /api/v1/social/providers              列出已启用的登录方式
 * - POST /api/v1/social/{provider}/session/    生成授权 URL（内嵌二维码用）
 * - POST /api/v1/social/token-exchange         用 TempAuth 码换 JWT
 *
 * 同源约定：session 端点是 Django View，state 存在 session cookie 里。开发环境由
 * Vite 的 /api 代理打到后端（见 vite.config.ts），因此这里一律用**相对路径**，
 * 让请求与前端同源，cookie 才能正常携带。若直连后端 origin，SameSite=Lax 下
 * 跨域 XHR 不带 cookie，回调时 Django 读不到 state 会判 invalid_session。
 */
import ky, { type KyInstance } from 'ky'

/** 社交登录专用客户端：不带 JWT（此时用户尚未登录），但需要带 cookie。 */
const socialClient: KyInstance = ky.create({
  credentials: 'same-origin',
  retry: 0,
})

export interface SocialProviderInfo {
  name: string
  display_name: string
  /** redirect：跳转到授权页；embedded_qr：前端渲染二维码 */
  login_mode: 'redirect' | 'embedded_qr'
  /** 渲染所需公开信息（app_id / authorize_url / 二维码尺寸），不含密钥 */
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
  goto: string
  state: string
  expires_in: number
}

export interface SocialTokenExchangeResponse {
  success: boolean
  access: string
  refresh: string
  user_id?: number
  username?: string
  message?: string
}

export const socialAuthApi = {
  async listProviders(): Promise<SocialProviderInfo[]> {
    try {
      const data = await socialClient.get('api/v1/social/providers').json<{ providers: SocialProviderInfo[] }>()
      return data.providers ?? []
    } catch {
      // 拉不到登录方式不应阻塞账密登录，静默降级
      return []
    }
  },

  /** 生成授权 URL（内嵌二维码用）。未配置该登录方式时后端返回 4xx。 */
  async createSession(provider: string): Promise<SocialSession> {
    // 不带尾斜杠：后端 ApiTrailingSlashMiddleware 会剥掉 /api/ 的尾斜杠
    return socialClient.post(`api/v1/social/${provider}/session`).json<SocialSession>()
  },

  /**
   * 用回调页拿到的一次性码换 JWT。
   * 业务错误是 HTTP 200 + { success: false, message }，需在此 throw 让上层处理。
   */
  async exchangeToken(code: string): Promise<SocialTokenExchangeResponse> {
    return socialClient.post('api/v1/social/token-exchange', { json: { code } }).json<SocialTokenExchangeResponse>()
  },
}
