/**
 * 前端触发下载的两个统一入口：本地合成的 Blob，以及后端给出的直链。
 *
 * 此前 5 处手写 `<a href=blob: download>`：全都漏了 URL.revokeObjectURL，
 * 每下载一次泄漏一份 Blob 内存（大文书 + 反复重下 → 页面内存线性上涨）。
 * 这里沿用 lib/pdf.ts 的先例（imageRegionBlob 的 finally 里回收）：
 * 用完即 revoke，且对「点完立刻 revoke」再留一个宏任务缓冲——
 * Firefox 的 a.click() 是异步派发的，同步 revoke 会导致下载取不到内容。
 */

/** 挂到 body 上点一下再摘下（a 是 inline 且点完立即移除，不参与布局） */
function clickAnchor(href: string, filename?: string): void {
  const a = document.createElement('a')
  a.href = href
  if (filename !== undefined) a.download = filename
  // 直链是跨源时 rel 必须给 noopener，否则新窗口能拿 window.opener 反控本页
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
}

/** 下载内存里的 Blob（前端合成：txt / md / docx 等），文件名显式给 */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  clickAnchor(url, filename)
  // 延到下一个宏任务再回收：Firefox 的 a.click() 是异步派发的，
  // 同步 revoke 会让它去取数据时 URL 已失效（下载得到空文件）
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

/**
 * 下载一个 URL（通常是带一次性下载票据的后端直链）。
 *
 * filename 省略时不设 download 属性，交给响应头 Content-Disposition 决定
 * （后端 FileResponse 带 as_attachment，文件名已在服务端重命名好）。
 * 此路径不涉及 ObjectURL，无需回收。
 */
export function downloadUrl(url: string, filename?: string): void {
  clickAnchor(url, filename)
}
