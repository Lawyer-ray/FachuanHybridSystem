import { API_BASE_URL } from '@/lib/api'

/**
 * 带鉴权的链接助手统一上提 lib/token（media 鉴权启用后 /media/ 直链同源同认证）。
 *
 * **安全审计 M-2**：返回 Promise——内部要向后端换一张 60 秒一次性下载票据，
 * 不再把 JWT 拼进 URL（会进 access log / 浏览器历史 / Referer）。
 */
export { withAuthToken } from '@/lib/token'

/** 下载直链用的 API 根（相对路径 /api/v1 或宿主注入的绝对地址） */
export { API_BASE_URL }

/**
 * 触发浏览器下载：后端 FileResponse 带 as_attachment，文件名由响应头给出。
 *
 * `urlWithAuth` 是**带鉴权的 URL 生成器**（内部会换下载票据），故本函数为
 * 异步：必须先取到票据才能发起下载。票据单次使用，每次下载都要重新生成。
 */
export async function triggerDownload(urlWithAuth: string | (() => Promise<string>)) {
  const url = typeof urlWithAuth === 'function' ? await urlWithAuth() : urlWithAuth
  const a = document.createElement('a')
  a.href = url
  a.download = ''
  document.body.appendChild(a)
  a.click()
  a.remove()
}
