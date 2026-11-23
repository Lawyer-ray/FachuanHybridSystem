import { PDF_RENDER_WIDTH } from './render-size'
import { pdfjsLib } from './pdfjs'

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
