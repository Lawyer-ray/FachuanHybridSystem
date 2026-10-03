import * as pdfjsLib from 'pdfjs-dist'
import PdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

pdfjsLib.GlobalWorkerOptions.workerSrc = PdfWorker

/**
 * pdf.js 6.x 的 JBIG2/CCITT G4（扫描件文字蒙版）与 JPEG2000 解码器是 WASM 实现，
 * 必须通过 wasmUrl 告知 wasm 文件目录（public/pdfjs/，构建时原样拷贝）。
 * 缺失时 pdf.js 默认 ignoreErrors=true 会**静默跳过**这些图像——典型症状：
 * 佳能扫描仪产的「JPEG 背景 + CCITT 文字蒙版」双图层 PDF 只剩淡影背景和印章，
 * 正文文字整层不渲染（PyMuPDF/浏览器原生查看器均正常，仅 pdf.js 不画）。
 */
const PDFJS_WASM_URL = `${import.meta.env.BASE_URL}pdfjs/`

export { pdfjsLib }

/** PDF 页渲染的目标像素宽度（CSS 宽度固定，交给父容器缩放） */
export const PDF_RENDER_WIDTH = 900

/** DPR 上限：3x 屏封到 2，避免单页位图内存翻倍（1920 宽 A4 ≈ 21MB RGBA） */
export const PDF_RENDER_DPR_CAP = 2

/** DPR=1（外接显示器）下的最低超采样倍率：1.5x 位图经浏览器下采样后，
 *  扫描件文字边缘明显锐于 1x 位图（实测锐度 +9.6%）；Retina 屏天然 ≥2x 不受影响。 */
export const PDF_RENDER_MIN_RATIO = 1.5

/** 渲染位图宽度上限（物理像素）：A4 @ ~164DPI，Retina 全宽下的清晰度已足够 */
export const PDF_RENDER_MAX_WIDTH = 1920

/**
 * 按显示需求计算渲染位图宽度：容器 CSS 宽 × max(devicePixelRatio, 1.5)（DPR 封顶 2）。
 *
 * 固定 900 物理像素的 canvas 在 Retina 屏上会被拉伸 ≥2 倍显示（900 位图
 * 摊到 1800+ 屏幕像素上，插值后文字发虚）——扫描件尤其明显。传入实际
 * 显示宽度后位图与屏幕像素 1:1，与原生查看器观感一致。
 *
 * dpr 参数仅为可测性（node 环境无 window），运行时取当前屏幕。
 */
export function pdfRenderWidthFor(cssWidth: number, dpr?: number): number {
  const ratio = dpr ?? (typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1)
  const effective = Math.max(Math.min(ratio, PDF_RENDER_DPR_CAP), PDF_RENDER_MIN_RATIO)
  return Math.round(Math.min(Math.max(Math.round(cssWidth * effective), PDF_RENDER_WIDTH), PDF_RENDER_MAX_WIDTH))
}

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
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve()
    img.onerror = () => reject(new Error('驻留图解码失败'))
    img.src = URL.createObjectURL(blob)
  })
  // blob URL 与 img 同生命周期驻留（不 revoke）：浏览器丢弃离屏解码位图后
  // 滚回时需经 src 重新解码，提前 revoke 会导致重解码失败页面空白。
  // 常驻成本仅为压缩数据（~250KB/页）。
  return img
}

/**
 * PDF 文档缓存：按 key（`messageId:partIndex`）保存已加载的文档与加载任务。
 *
 * 为什么是 Map 而不是单槽：一个材料包会同时渲染它名下所有 PDF 的页（Flow 给每页都挂一个
 * PageCell，且 React.StrictMode 双跑 effect），loadPdfDocument 会被多个不同 key 并发调用。
 * 旧实现是单槽 + ``cachedTask.destroy()``：加载新 key 时把上一个文档连同 worker 一起干掉，
 * 而 pdf.js 的 MessageHandler.destroy() 只 abort 监听、不 reject 挂起的 sendWithPromise，
 * 于是正在渲染的那页 promise 永远 pending、页卡一直转骨架屏；并发改写 cachedDocKey 也让同一
 * key 的命中判断失效。改为按 key 常驻，关阅读器时再用 clearPdfDocuments() 统一释放。
 */
interface PdfCacheEntry {
  task: pdfjsLib.PDFDocumentLoadingTask
  doc: Promise<pdfjsLib.PDFDocumentProxy>
}
const docCache = new Map<string, PdfCacheEntry>()

/**
 * 加载一份 PDF 文档并按 key 缓存（同一附件只加载一次）。
 * data 由调用方通过带鉴权的请求取回。
 *
 * 注意：pdf.js 会把 getDocument({ data }) 里的 ArrayBuffer **transfer** 给 worker
 * （pdf.mjs: sendWithPromise("GetDocRequest", docParams, [data.buffer])），被 transfer 的
 * buffer 会 detach、byteLength 归零。调用方（material-prep 的 fetchAttachmentBytes）会把同一份
 * buffer 反复拿去渲染/OCR/上传，直接传本体就会把它废掉——所以这里必须传副本，本体留给别人用。
 *
 * 并发同 key 的调用复用缓存的加载 promise，不会重复 getDocument；加载失败则撤掉缓存以便重试。
 */
export function loadPdfDocument(key: string, data: ArrayBuffer): Promise<pdfjsLib.PDFDocumentProxy> {
  const hit = docCache.get(key)
  if (hit) return hit.doc
  // 副本给 pdf.js：它会把副本 transfer 给 worker，data 本体保持可用
  const task = pdfjsLib.getDocument({ data: data.slice(0), wasmUrl: PDFJS_WASM_URL })
  const entry: PdfCacheEntry = { task, doc: task.promise }
  docCache.set(key, entry)
  entry.doc.catch(() => {
    if (docCache.get(key) === entry) docCache.delete(key)
  })
  return entry.doc
}

/** 关闭并清空全部已缓存的 PDF 文档与 worker（退出阅读器时调用，避免跨包累积占内存）。 */
export function clearPdfDocuments(): void {
  for (const [key, entry] of docCache) {
    docCache.delete(key)
    void entry.task.destroy().catch(() => {
      /* noop */
    })
  }
}

/** 全局清理入口（登出时调用）：清空 PDF 文档缓存，语义与 clearPdfDocuments 一致。 */
export function clearPdfCache(): void {
  clearPdfDocuments()
}

/** 把 PDF 的一页渲染到 canvas，返回画好的 canvas（未附加到 DOM）。 */
export async function renderPdfPage(
  pdf: pdfjsLib.PDFDocumentProxy,
  pageNum: number,
  targetWidth = PDF_RENDER_WIDTH,
): Promise<HTMLCanvasElement> {
  const page = await pdf.getPage(pageNum)
  const base = page.getViewport({ scale: 1 })
  const scale = targetWidth / base.width
  const viewport = page.getViewport({ scale })
  const canvas = document.createElement('canvas')
  canvas.width = Math.floor(viewport.width)
  canvas.height = Math.floor(viewport.height)
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('无法创建 canvas 2d 上下文')
  await page.render({ canvas, viewport }).promise
  return canvas
}

/** 0-1 归一化矩形（OCR 框取字） */
export interface NormRect {
  x: number
  y: number
  w: number
  h: number
}

/** 渲染 PDF 一页并裁出归一化矩形区域，返回画好的 canvas（四周留一点空白）。 */
export async function renderPdfPageRegion(
  pdf: pdfjsLib.PDFDocumentProxy,
  pageNum: number,
  rect: NormRect,
  targetWidth = 1600,
): Promise<HTMLCanvasElement> {
  const full = await renderPdfPage(pdf, pageNum, targetWidth)
  const pad = 0.02
  const cw = Math.max(32, Math.round(full.width * rect.w))
  const ch = Math.max(32, Math.round(full.height * rect.h))
  const canvas = document.createElement('canvas')
  canvas.width = Math.min(full.width, cw + Math.round(targetWidth * pad * 2))
  canvas.height = Math.min(full.height, ch + Math.round(targetWidth * pad * 2))
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('无法创建 canvas 2d 上下文')
  ctx.fillStyle = '#ffffff'
  ctx.fillRect(0, 0, canvas.width, canvas.height)
  const sx = Math.max(0, full.width * rect.x - Math.round(targetWidth * pad))
  const sy = Math.max(0, full.height * rect.y - Math.round(targetWidth * pad))
  ctx.drawImage(full, sx, sy, canvas.width, canvas.height, 0, 0, canvas.width, canvas.height)
  return canvas
}

/** 把图片字节裁出归一化矩形区域，返回 PNG Blob。 */
export async function imageRegionBlob(bytes: ArrayBuffer, rect: NormRect): Promise<Blob> {
  const url = URL.createObjectURL(new Blob([bytes]))
  try {
    const img = new Image()
    await new Promise<void>((res, rej) => {
      img.onload = () => res()
      img.onerror = () => rej(new Error('图片解码失败'))
      img.src = url
    })
    const pad = 0.02
    const cw = Math.max(32, Math.round(img.width * rect.w))
    const ch = Math.max(32, Math.round(img.height * rect.h))
    const canvas = document.createElement('canvas')
    canvas.width = Math.min(img.width, cw + Math.round(img.width * pad * 2))
    canvas.height = Math.min(img.height, ch + Math.round(img.height * pad * 2))
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('无法创建 canvas 2d 上下文')
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    const sx = Math.max(0, img.width * rect.x - Math.round(img.width * pad))
    const sy = Math.max(0, img.height * rect.y - Math.round(img.height * pad))
    ctx.drawImage(img, sx, sy, canvas.width, canvas.height, 0, 0, canvas.width, canvas.height)
    return await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('PNG 编码失败'))), 'image/png')
    })
  } finally {
    URL.revokeObjectURL(url)
  }
}

/** 把 canvas 编码成 PNG Blob */
export function canvasToBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('PNG 编码失败'))), 'image/png')
  })
}
