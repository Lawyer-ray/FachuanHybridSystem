import * as pdfjsLib from 'pdfjs-dist'
import PdfWorker from 'pdfjs-dist/build/pdf.worker.min.mjs?url'

pdfjsLib.GlobalWorkerOptions.workerSrc = PdfWorker

export { pdfjsLib }

/** PDF 页渲染的目标像素宽度（CSS 宽度固定，交给父容器缩放） */
export const PDF_RENDER_WIDTH = 900

let cachedDoc: pdfjsLib.PDFDocumentProxy | null = null
let cachedDocKey = ''

/**
 * 加载一份 PDF 文档并按 key 缓存（同一附件只加载一次）。
 * data 由调用方通过带鉴权的请求取回。
 */
export async function loadPdfDocument(key: string, data: ArrayBuffer): Promise<pdfjsLib.PDFDocumentProxy> {
  if (cachedDoc && cachedDocKey === key) return cachedDoc
  if (cachedDoc) {
    try {
      await cachedDoc.destroy()
    } catch {
      /* noop */
    }
  }
  const doc = await pdfjsLib.getDocument({ data }).promise
  cachedDoc = doc
  cachedDocKey = key
  return doc
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
  await page.render({ canvasContext: ctx, viewport }).promise
  return canvas
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
