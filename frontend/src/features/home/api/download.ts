import { API_BASE_URL } from '@/lib/api'

/** 带 token 的链接助手统一上提 lib/token（media 鉴权启用后 /media/ 直链同源同认证）。 */
export { withAuthToken } from '@/lib/token'

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
