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
 * cookie 不会随跨域 XHR 发送。因此这里一律用同源路径，让请求经 Vite 代理
 * （见 vite.config.ts）与后端同源；若直连后端 origin，回调时 Django 读不到
 * state 会判 invalid_session。
 *
 * 两个客户端的路径写法不同：
 * - socialClient 无 prefix，必须用以 / 开头的绝对路径——ky 按「当前文档目录」
 *   解析相对路径，`api/v1/...` 在 `/settings/bindings` 下会变成
 *   `/settings/api/v1/...`，被 SPA fallback 返回 index.html，报 JSON 解析失败。
 * - authedSocialClient 来自 createApiClient（prefix=/api/v1），传相对段
 *   `social/...`，ky 在 join 边界归一化拼出 /api/v1/social/...。
 */
import ky, { type KyInstance } from 'ky'
import { createApiClient } from '@/lib/api'
import { setTokens } from '@/lib/token'
import type { components, operations } from '@/types/api-schema'

/** 未登录即可用的客户端：不带 JWT，但要带 cookie（state 在 session 里）。
 *  豁免统一出口 createApiClient 的原因：登录前的匿名请求没有可刷新的 token，
 *  createApiClient 的 401 处理会走「刷新失败 → 跳转 /login」，把登录页用户
 *  甩进重定向环；这里失败只需原地抛错，由调用方降级（如 listProviders 静默）。 */
const socialClient: KyInstance = ky.create({
  credentials: 'same-origin',
  retry: 0,
})

/** 已登录才可用的客户端：复用 lib/api 统一出口（JWT 注入、401 单飞刷新重试）。
 *  透传 credentials: 'same-origin'——绑定授权的 state 存 Django session cookie，
 *  必须随同源请求携带；retry: 0——授权会话是后端 session 单槽写入（见下文
 *  shareInflightSession），ky 自动重试会覆盖在途 state，必须关掉。 */
const authedSocialClient = createApiClient({ credentials: 'same-origin', retry: 0 })

/** 已启用的社交登录方式（GET /social/providers 的行，生成物 ProviderOut）。
 *  client_config 是渲染所需公开信息（app_id / authorize_url / 二维码尺寸等，
 *  生成物按 dict 收成字符串索引签名），不含密钥；provider-catalog 里为 null
 *  表示该平台尚未配置启用。 */
export type SocialProviderInfo = Omit<components['schemas']['ProviderOut'], 'login_mode'> & {
  /** 覆写收窄：生成物按后端 str 字段声明为裸 string；前端只实现两种渲染
   *  形态，收窄成字面量联合让分派漏分支在编译期暴露（未知值由 login-methods
   *  的 toKind 运行时兜底为 redirect，不会漏处理）。 */
  login_mode: 'redirect' | 'embedded_qr'
}

/** providers 列表信封：行类型用收窄后的 SocialProviderInfo（login_mode 两值联合）。
 *  生成物行是裸 string，后端实际只产出这两种值；信封本体仍投影生成物，
 *  后端增删字段时 tsc 能跟着报警。 */
type SocialProvidersEnvelope = Omit<components['schemas']['ProvidersListOut'], 'providers'> & {
  providers: SocialProviderInfo[]
}

/** 授权会话（POST /social/{provider}/session 的响应）。
 *  生成物组件名 SessionOut 与 OA 归档等域共用同名单例，为钉死 social 契约
 *  按 operation 投影。success / message 生成物为必有（Schema 带默认值），与
 *  旧手写版的可选不同，以生成物为准——消费方均已做空串兜底。 */
export type SocialSession = operations['apps_social_auth_api_social_auth_api_create_session']['responses'][200]['content']['application/json']

/** 用 TempAuth 码换 JWT 的响应（POST /social/token-exchange，生成物 TokenExchangeOut）。
 *  username / message 生成物为必有（Schema @default ''），以生成物为准。 */
export type SocialTokenExchangeResponse = components['schemas']['TokenExchangeOut']

/** 当前用户已绑定的社交账号（GET /social/bindings 的行，生成物 BoundAccountOut） */
export type BoundAccount = components['schemas']['BoundAccountOut']

/** 生成授权 URL 的通用封装：业务失败是 200 + success:false，必须在这里 throw。 */
async function requestSession(client: KyInstance, path: string): Promise<SocialSession> {
  const data = await client.post(path).json<SocialSession>()
  if (data.success === false) {
    throw new Error(data.message || '该登录方式暂不可用')
  }
  return data
}

/**
 * in-flight 的授权会话请求去重。
 *
 * 后端把 state 存在 Django session 的**单槽**键里（views.py 的 session["oauth"]），
 * 新请求直接覆盖旧值。若同一浏览器并发发两次 session 请求（React StrictMode 双挂载
 * 是必然发生的），两个响应的渲染顺序与后端写入顺序一旦颠倒，屏幕上二维码携带的
 * state 就和 session 里最后写入的不一致——扫码回调必然 invalid_state（「安全校验
 * 失败，请重新扫码」）。并发调用共享同一 promise 后，只有一个 state 被写入和渲染，
 * 天然一致；in-flight 结束后清除，后续刷新二维码（合法的重新挂载）仍拿新 state。
 */
const sessionInflight = new Map<string, Promise<SocialSession>>()

function shareInflightSession(key: string, run: () => Promise<SocialSession>): Promise<SocialSession> {
  const existing = sessionInflight.get(key)
  if (existing) return existing
  const p = run().finally(() => {
    if (sessionInflight.get(key) === p) sessionInflight.delete(key)
  })
  sessionInflight.set(key, p)
  return p
}

/** 已启用登录方式的 query key（与 socialAuthApi.listProviders 配套） */
export const SOCIAL_PROVIDERS_KEY = ['social-providers'] as const

export const socialAuthApi = {
  async listProviders(): Promise<SocialProviderInfo[]> {
    try {
      const data = await socialClient.get('/api/v1/social/providers').json<SocialProvidersEnvelope>()
      return data.providers ?? []
    } catch {
      // 拉不到登录方式不应阻塞账密登录，静默降级
      return []
    }
  },

  /** 生成授权 URL（内嵌二维码用）。未配置该登录方式时后端返回 200 + success:false。 */
  async createSession(provider: string): Promise<SocialSession> {
    // 不带尾斜杠：后端 ApiTrailingSlashMiddleware 会剥掉 /api/ 的尾斜杠
    return shareInflightSession(`login:${provider}`, () =>
      requestSession(socialClient, `/api/v1/social/${provider}/session`),
    )
  },

  /**
   * 用回调页拿到的一次性码换 JWT。
   * 业务错误是 HTTP 200 + { success: false, message }，需在此 throw 让上层处理。
   */
  async exchangeToken(code: string): Promise<SocialTokenExchangeResponse> {
    const data = await socialClient
      .post('/api/v1/social/token-exchange', { json: { code } })
      .json<SocialTokenExchangeResponse>()

    // token 落 localStorage 是 API 层的责任（与 authApi.login 同一约定）。
    // 漏了这步，回调页跳回受保护路由时 RequireAuth 只看 hasToken()，会把刚
    // 登录成功的用户立刻打回登录页——表现就是「扫码后闪回登录页」。
    if (data.success && data.access && data.refresh) {
      setTokens({ access: data.access, refresh: data.refresh })
    }
    return data
  },
}

export const socialBindingsApi = {
  /** 当前用户已绑定的社交账号（响应为生成物 BoundAccountsOut）。 */
  async list(): Promise<BoundAccount[]> {
    const data = await authedSocialClient.get('social/bindings').json<components['schemas']['BoundAccountsOut']>()
    return data.accounts ?? []
  },

  /** 全部已知 Provider：client_config 为 null 表示平台未启用，前端显示灰态。 */
  async catalog(): Promise<SocialProviderInfo[]> {
    const data = await authedSocialClient
      .get('social/provider-catalog')
      .json<SocialProvidersEnvelope>()
    return data.providers ?? []
  },

  /**
   * 发起绑定授权。授权完成后后端把身份关联到当前登录用户，不新建律师账号。
   * 用箭头函数属性（而非方法简写）：调用方需要稳定的方法引用传入子组件
   * （见 BindProviderDialog），箭头属性不依赖 this，解绑传引用是安全的。
   */
  createBindSession: async (provider: string, redirect = '/settings/bindings'): Promise<SocialSession> => {
    // 与登录会话同样的单槽覆盖问题（bind_user_id 不同也不该并发），key 里带 redirect 归组
    return shareInflightSession(`bind:${provider}:${redirect}`, () =>
      requestSession(
        authedSocialClient,
        `social/${provider}/bind-session?redirect=${encodeURIComponent(redirect)}`,
      ),
    )
  },

  /** 解绑。未绑定该平台时后端返回 success:false（响应为生成物 UnbindOut）。 */
  async unbind(provider: string): Promise<components['schemas']['UnbindOut']> {
    return authedSocialClient.delete(`social/${provider}/bind`).json<components['schemas']['UnbindOut']>()
  },
}
