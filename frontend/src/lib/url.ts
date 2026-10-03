/** 后端可写字段直通 href/src 前的 scheme 白名单守卫（防 javascript: 存储型注入）。 */
export function safeHttpUrl(url: string | null | undefined, fallback = ''): string {
  if (!url) return fallback
  try {
    // node 单测无 window，用固定 base；浏览器内按当前 origin 解析相对路径
    const base = typeof window === 'undefined' ? 'http://localhost' : window.location.origin
    const u = new URL(url, base)
    return u.protocol === 'http:' || u.protocol === 'https:' ? u.toString() : fallback
  } catch {
    return fallback
  }
}
