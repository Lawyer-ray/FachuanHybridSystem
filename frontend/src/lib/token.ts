/**
 * JWT Token 管理
 * 处理 access token 和 refresh token 的存储、获取、刷新
 */

const ACCESS_TOKEN_KEY = 'access_token'
const REFRESH_TOKEN_KEY = 'refresh_token'

/**
 * Token 响应类型
 */
export interface TokenPair {
  access: string
  refresh: string
}

/**
 * 获取 access token
 */
export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY)
}

/**
 * 获取 refresh token
 */
export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

/**
 * 保存 token pair
 */
export function setTokens(tokens: TokenPair): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access)
  localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh)

  // 通知 macOS Native 应用（如果在 WebView 中运行）
  notifyNativeAuth(tokens)
}

/**
 * 通知 macOS Native 应用 Token 已更新
 * 仅在 macOS WebView 环境中生效
 */
function notifyNativeAuth(tokens: TokenPair): void {
  try {
    // 检查是否在 macOS WebView 环境中
    const webkit = (window as unknown as { webkit?: { messageHandlers?: { nativeAuth?: { postMessage: (msg: unknown) => void } } } }).webkit
    if (webkit?.messageHandlers?.nativeAuth) {
      webkit.messageHandlers.nativeAuth.postMessage({
        type: 'tokenUpdate',
        access: tokens.access,
        refresh: tokens.refresh,
      })
    }
  } catch {
    // 静默忽略错误（非 Native 环境）
  }
}

/**
 * 清除所有 token
 */
export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)

  // 通知 macOS Native 应用用户已登出
  notifyNativeLogout()
}

/**
 * 通知 macOS Native 应用用户已登出
 */
function notifyNativeLogout(): void {
  try {
    const webkit = (window as unknown as { webkit?: { messageHandlers?: { nativeAuth?: { postMessage: (msg: unknown) => void } } } }).webkit
    if (webkit?.messageHandlers?.nativeAuth) {
      webkit.messageHandlers.nativeAuth.postMessage({
        type: 'logout',
      })
    }
  } catch {
    // 静默忽略错误
  }
}

/**
 * 检查是否有 token
 */
export function hasToken(): boolean {
  return !!getAccessToken()
}

/**
 * 解析 JWT token payload（不验证签名）
 */
function parseJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const base64Url = token.split('.')[1]
    if (!base64Url) return null // 不是三段式 JWT，无需进 try 里的解码链
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/')
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    )
    // JSON.parse 返回 any，收窄成本函数声明的 payload 类型
    return JSON.parse(jsonPayload) as Record<string, unknown>
  } catch {
    return null
  }
}

/**
 * 检查 token 是否过期
 */
export function isTokenExpired(token: string): boolean {
  const payload = parseJwtPayload(token)
  if (!payload || typeof payload.exp !== 'number') {
    return true
  }
  // 提前 30 秒认为过期，避免边界情况
  return Date.now() >= (payload.exp - 30) * 1000
}

/**
 * 检查 access token 是否需要刷新
 */
export function shouldRefreshToken(): boolean {
  const token = getAccessToken()
  if (!token) return false
  return isTokenExpired(token)
}

/**
 * 带鉴权的链接地址助手（<a href> / <img src> / iframe 等带不上请求头的场景）。
 *
 * 后端 JWTOrSessionAuth 专门为下载/预览场景支持 `?token=` 查询参数
 * （apps/core/security/auth.py）；media 鉴权启用后 /media/ 直链也走同一
 * 认证（apps/core/api/media_protected.py），因此所有指向后端的裸链接都
 * 应经本函数拼 token。token 缺失（session 登录态）时原样返回，交给 cookie。
 */
export function withAuthToken(path: string): string {
  // node 单测环境无 localStorage（与 lib/api 的 getApiBaseUrl 同款防御）
  const token = typeof localStorage === 'undefined' ? null : getAccessToken()
  if (!token) return path
  return `${path}${path.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`
}
