/**
 * API Client
 * 通用 API 客户端，带 JWT 认证
 */

import ky, { type KyInstance, type Options } from 'ky'

import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
  shouldRefreshToken,
} from './token'

/**
 * 获取 API 基础路径（localStorage 优先，fallback 到环境变量）。
 *
 * 默认用**相对路径** `/api/v1`：dev 由 Vite proxy 转发到后端，生产按同源部署，
 * 都不需要写死 host。（社交登录的 session cookie 也要求与后端同源，见
 * features/auth/social-api.ts 的说明——整站统一同源约定，避免两套 URL 体系。）
 * localStorage 里若被 Native 壳等宿主写入了 api_base_url，仍然优先生效。
 */
export function getApiBaseUrl(): string {
  // node 单测环境无 localStorage（模块加载期就会读本函数），跳过读取
  const stored = typeof localStorage === 'undefined' ? null : localStorage.getItem('api_base_url')
  // import.meta.env 自定义变量类型是 any（vite/client 的索引签名），as 收窄成可选字符串
  const envBase = import.meta.env.VITE_API_BASE_URL as string | undefined
  return stored || envBase || '/api/v1'
}

/** 模块级缓存，避免每次调用都读 localStorage */
export const API_BASE_URL = getApiBaseUrl()

/**
 * Token 刷新响应
 *
 * refresh 可选：后端 SIMPLE_JWT 已启用 ROTATE_REFRESH_TOKENS +
 * BLACKLIST_AFTER_ROTATION（安全审计 M-8），每次刷新都会返回**新的**
 * refresh token，同时旧的立即进黑名单。若沿用旧 refresh，下一次刷新必然
 * 拿到「Token is blacklisted」而静默掉线。
 */
interface TokenRefreshResponse {
  access: string
  refresh?: string
}

/**
 * 是否正在刷新 token
 */
let isRefreshing = false
let refreshPromise: Promise<string | null> | null = null

/**
 * 跨 tab 刷新协调：多请求/多 tab 并发 401 时统一只发一次刷新、其余共享结果，
 * 避免重复刷新互相覆盖。后端已启用 refresh token 轮换（ROTATE_REFRESH_TOKENS
 * + BLACKLIST_AFTER_ROTATION，安全审计 M-8）——旧 refresh 会被首次刷新消费
 * 并拉黑，所以「只刷一次、其余 tab 共享结果」不是优化而是**必需**：两个 tab
 * 同时用同一个旧 refresh 刷新，后到的那次会直接拿到「Token is blacklisted」。
 * 协议：刷新方先写时间戳租约（auth:refresh-lease），成功后写完成信号
 * （auth:refresh-done，storage 事件只在其他 tab 触发）；其他 tab 发现
 * 新鲜租约就等信号共享新 token，而不是自己也去刷。
 */
const REFRESH_LEASE_KEY = 'auth:refresh-lease'
const REFRESH_DONE_KEY = 'auth:refresh-done'

/** 租约新鲜窗口：超过视为持约 tab 已死（崩溃/卡死），可自行刷新 */
const REFRESH_LEASE_MS = 10_000

/** 等待其他 tab 完成信号的上限，超时后自行重试一次 */
const REFRESH_WAIT_MS = 3_000

/** 判断刷新租约是否仍在有效期内（纯函数，便于单测）。 */
export function isLeaseFresh(lease: string | null, now = Date.now(), maxAge = REFRESH_LEASE_MS): boolean {
  if (lease === null) return false
  const ts = Number(lease)
  // ts > 0：挡掉 ''/'abc' 这类脏值（Number('') 是 0，会被窗口判定误判为新鲜）
  return Number.isFinite(ts) && ts > 0 && now - ts < maxAge
}

/** 等待其他 tab 写入的刷新完成信号（storage 事件）。无论等到与否都 resolve，由调用方自决。 */
function waitForRefreshDoneSignal(timeoutMs = REFRESH_WAIT_MS): Promise<void> {
  return new Promise((resolve) => {
    const finish = () => {
      window.removeEventListener('storage', onStorage)
      clearTimeout(timer)
      resolve()
    }
    const onStorage = (e: StorageEvent) => {
      if (e.key === REFRESH_DONE_KEY) finish()
    }
    const timer = setTimeout(finish, timeoutMs)
    window.addEventListener('storage', onStorage)
  })
}

/**
 * 持租约执行刷新：写 lease → 刷新 → 广播 done 信号，finally 撤租约。
 */
async function refreshWithLease(): Promise<string> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) {
    throw new Error('No refresh token')
  }

  localStorage.setItem(REFRESH_LEASE_KEY, String(Date.now()))
  try {
    const response = await ky
      .post(`${API_BASE_URL}/token/refresh`, {
        json: { refresh: refreshToken },
      })
      .json<TokenRefreshResponse>()

    // 轮换语义（M-8）：后端返回的新 refresh 必须落库，否则下一次刷新拿的是
    // 已被拉黑的旧 token。后端未返回（未开轮换的部署）时沿用旧的，保持兼容。
    setTokens({
      access: response.access,
      refresh: response.refresh ?? refreshToken,
    })
    // 广播给等待中的 tab（storage 事件只在写入方以外的页面触发）
    localStorage.setItem(REFRESH_DONE_KEY, String(Date.now()))

    return response.access
  } finally {
    localStorage.removeItem(REFRESH_LEASE_KEY)
  }
}

/**
 * 刷新 access token（跨 tab 协调）：其他 tab 持新鲜租约时等它完成并共享
 * 新 token；等不到信号（3s 超时）或新 token 仍不可用时，自行重试一次。
 */
async function refreshAccessToken(): Promise<string> {
  if (isLeaseFresh(localStorage.getItem(REFRESH_LEASE_KEY))) {
    await waitForRefreshDoneSignal()
    const shared = getAccessToken()
    if (shared && !shouldRefreshToken()) return shared
  }
  return refreshWithLease()
}

/**
 * 单飞刷新 access token：本 tab 并发调用共享同一个 Promise，只发一次 /token/refresh；
 * 跨 tab 的一致性由 refreshAccessToken 内的租约协调兜底。
 * 刷新失败时清空令牌并返回 null（不抛出，由调用方决定如何处置）。
 */
function refreshAccessTokenSingleFlight(): Promise<string | null> {
  if (isRefreshing && refreshPromise) {
    return refreshPromise
  }

  isRefreshing = true
  refreshPromise = refreshAccessToken()
    .catch(() => {
      clearTokens()
      return null
    })
    .finally(() => {
      isRefreshing = false
      refreshPromise = null
    })

  return refreshPromise
}

/**
 * 获取有效的 access token
 */
async function getValidAccessToken(): Promise<string | null> {
  const token = getAccessToken()
  if (!token) return null

  if (shouldRefreshToken()) {
    return refreshAccessTokenSingleFlight()
  }

  return token
}

/**
 * 创建带 JWT 认证的 API 客户端
 */
export function createApiClient(options?: Options): KyInstance {
  return ky.create({
    prefix: API_BASE_URL,
    ...options,
    hooks: {
      beforeRequest: [
        async ({ request }) => {
          const token = await getValidAccessToken()
          if (token) {
            request.headers.set('Authorization', `Bearer ${token}`)
          }
        },
        ...(options?.hooks?.beforeRequest || []),
      ],
      afterResponse: [
        async ({ request, response, retryCount }) => {
          if (response.status === 401 && !request.url.includes('/token/') && retryCount === 0) {
            // 复用单飞刷新：并发请求同时 401 时只发一次 refresh，
            // 否则后续请求会拿已被首个请求消费掉的 refresh token 误判会话失效
            const newToken = await refreshAccessTokenSingleFlight()
            if (!newToken) {
              window.location.href = '/login'
              throw new Error('Session expired')
            }
            const retryRequest = new Request(request, {
              headers: new Headers(request.headers),
            })
            retryRequest.headers.set('Authorization', `Bearer ${newToken}`)
            // 走 ky.retry 强制重试：复用本实例的完整选项（含请求级 timeout——上传类
            // 300s；hook 收到的 options 已被 ky 剥掉 timeout，raw ky() 又会退回默认
            // 10s 误杀大上传）。retryCount === 0 守卫防止重试再 401 时无限刷新
            return ky.retry({ request: retryRequest })
          }
          return response
        },
        ...(options?.hooks?.afterResponse || []),
      ],
    },
  })
}

/**
 * 默认 API 客户端实例
 */
export const api = createApiClient()

/**
 * 上传类请求超时：ky 默认仅 10s，多文件整包上传（如 90+ 页扫描包）必被误杀，
 * 参照 parseDocument 的 300s 口径统一放行（convertDocument 90s 是转换等待，不含大上传）。
 */
export const UPLOAD_TIMEOUT_MS = 300_000

export default api
