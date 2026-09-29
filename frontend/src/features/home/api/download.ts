import { API_BASE_URL } from '@/lib/api'
import { getAccessToken } from '@/lib/token'

/**
 * 带鉴权的下载地址助手。
 *
 * 前端 API 走 JWT Bearer 头，但 <a href> 这类纯链接下载带不上请求头。
 * 后端 JWTOrSessionAuth 专门为下载场景支持 `?token=` 查询参数
 * （apps/core/security/auth.py），所以这里把当前 access token 拼进 URL。
 * token 缺失（如 session 登录态）时原样返回，交给 cookie 鉴权。
 */
export function withAuthToken(path: string): string {
  const token = getAccessToken()
  if (!token) return path
  return `${path}${path.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`
}

/** 下载直链用的 API 根（相对路径 /api/v1 或宿主注入的绝对地址） */
export { API_BASE_URL }

/** 触发浏览器下载：后端 FileResponse 带 as_attachment，文件名由响应头给出 */
export function triggerDownload(url: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = ''
  document.body.appendChild(a)
  a.click()
  a.remove()
}
