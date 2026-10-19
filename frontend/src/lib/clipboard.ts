/**
 * 复制文本到剪贴板（跨 feature 通用：workbench / home 工具卡共用）。
 *
 * navigator.clipboard 优先（安全上下文 / 用户手势下的标准路径），不可用或被拒
 * （如非 https 的远程部署、旧浏览器）时降级到隐藏 textarea + execCommand。
 * 只负责写剪贴板并报告成败，不弹 toast——提示文案各调用方自己掌握。
 */

export async function copyText(text: string): Promise<boolean> {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      /* 落到兜底 */
    }
  }
  // 无 DOM（SSR / node 环境单测）时没有 execCommand 可言，如实报失败
  if (typeof document === 'undefined') return false
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  try {
    return document.execCommand('copy')
  } catch {
    /* 极老浏览器连 execCommand 都没有：如实报告失败 */
    return false
  } finally {
    ta.remove()
  }
}
