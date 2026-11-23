/**
 * 驻留 img → blob URL 登记表：canvasToRetainedImg 创建时登记，
 * 替换/卸载时经 releaseRetainedImg 回收——否则 ObjectURL 永不释放，
 * 重渲（宽度/DPR/页码变化）一次泄漏一条，大包反复缩放会线性堆积。
 */
const retainedImgUrls = new Map<HTMLImageElement, string>()

/**
 * 把渲染好的 canvas 转成驻留 <img>（WebP，退 JPEG）：编码完成后替换 DOM。
 *
 * 为什么要换：离屏 canvas 的位图内存（1920 宽 A4 ≈ 21MB/页）由页面持有、
 * 浏览器无法回收——92 页大包滚完即 ~1.9GB。换成 <img> 后浏览器只保留
 * 压缩数据（~250KB/页），离屏时自动丢弃解码位图、滚回时快速重解码。
 * 显示中的画面无缝（先挂 canvas、编码完成再替换），清晰度无损于 CSS 拉伸。
 */
export async function canvasToRetainedImg(canvas: HTMLCanvasElement, quality = 0.9): Promise<HTMLImageElement> {
  const encode = (type: string) =>
    new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, type, quality))
  const blob = (await encode('image/webp')) ?? (await encode('image/jpeg'))
  if (!blob) throw new Error('canvas 编码失败')
  const img = new Image()
  img.decoding = 'async'
  const url = URL.createObjectURL(blob)
  retainedImgUrls.set(img, url)
  try {
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve()
      img.onerror = () => reject(new Error('驻留图解码失败'))
      img.src = url
    })
  } catch (err) {
    // 解码失败的 img 不会再被挂载，就地回收登记，不让 ObjectURL 悬挂到页面卸载
    releaseRetainedImg(img)
    throw err
  }
  // blob URL 与 img 同生命周期驻留：浏览器丢弃离屏解码位图后滚回时需经 src
  // 重新解码，驻留期间 revoke 会导致重解码失败页面空白——所以只在替换/卸载
  // 旧 img 时调用 releaseRetainedImg 回收。常驻成本仅为压缩数据（~250KB/页）。
  return img
}

/**
 * 回收驻留 img 的 blob URL（重渲替换旧 img / 组件卸载时调用）。
 * 幂等：未登记（已回收 / 非驻留图）的直接 no-op，可放心在清理路径重复调。
 */
export function releaseRetainedImg(img: HTMLImageElement): void {
  const url = retainedImgUrls.get(img)
  if (url === undefined) return
  retainedImgUrls.delete(img)
  URL.revokeObjectURL(url)
}
