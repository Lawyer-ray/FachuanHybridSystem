/**
 * 下载票据助手（安全审计 M-2）。
 *
 * 后端不再接受 `?token=<JWT>`——完整 JWT 会落入 nginx access log /
 * 浏览器历史 / Referer 头，拿到即等于拿到身份。改为换取 **60 秒一次性
 * 下载票据**（`POST /api/v1/download-ticket`）拼 `?ticket=`。票据只含
 * user_id，泄露也换不来长期凭证。
 *
 * 放在独立模块而非 lib/token.ts：后者被 lib/api.ts 静态依赖，在这里 import
 * api 会形成循环依赖（token → api → token）。本模块只被下载/预览路径引用。
 */

import { api } from './api'

/** 把票据追加到 URL 的 query string（保留既有参数） */
export function appendTicket(url: string, ticket: string): string {
  if (!ticket) return url
  const sep = url.includes('?') ? '&' : '?'
  return `${url}${sep}ticket=${encodeURIComponent(ticket)}`
}

/** 移除 URL 上的票据参数（日志 / 展示用，避免票据进日志） */
export function stripTicket(url: string): string {
  return url.replace(/([?&])ticket=[^&]*(&|$)/, (_m, lead: string, tail: string) => (tail ? lead : ''))
}

/**
 * 为 URL 换取下载票据并拼接。
 *
 * 失败（未登录 / 换票接口异常）时返回原始 url：由后端按 403 处理，比在前端
 * 静默改掉 href 更容易定位。票据为**单次使用**，同一 URL 重复触发下载需
 * 重新调用本函数，不要缓存返回值复用。
 */
export async function withDownloadTicket(path: string): Promise<string> {
  try {
    const res = await api.post('download-ticket', { json: { resource: path.slice(0, 200) } }).json<{ ticket: string }>()
    return appendTicket(path, res.ticket)
  } catch {
    return path
  }
}
