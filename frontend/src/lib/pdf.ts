import * as pdfjsLib from 'pdfjs-dist'
import PdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

pdfjsLib.GlobalWorkerOptions.workerSrc = PdfWorker

export { pdfjsLib }

/** PDF 页渲染的目标像素宽度（CSS 宽度固定，交给父容器缩放） */
export const PDF_RENDER_WIDTH = 900

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
  const task = pdfjsLib.getDocument({ data: data.slice(0) })
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

/** 把 PDF 的一页渲染成 PNG Blob（供 OCR 框选取字上传）。 */
export async function renderPdfPageBlob(
  pdf: pdfjsLib.PDFDocumentProxy,
  pageNum: number,
  targetWidth = PDF_RENDER_WIDTH,
): Promise<Blob> {
  const canvas = await renderPdfPage(pdf, pageNum, targetWidth)
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('PNG 编码失败'))), 'image/png')
  })
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

/** 根据附件 content_type / 文件名推断素材类型 */
export function detectMaterialKind(contentType: string | undefined, filename: string): 'pdf' | 'photo' | 'office' {
  const ct = (contentType || '').toLowerCase()
  const name = filename.toLowerCase()
  if (ct.includes('pdf') || name.endsWith('.pdf')) return 'pdf'
  if (
    ct.startsWith('image/') ||
    /\.(jpe?g|png|gif|webp|bmp|heic|heif|tiff?)$/.test(name)
  ) {
    return 'photo'
  }
  return 'office'
}
