import { PDF_RENDER_WIDTH } from './render-size'
import { pdfjsLib } from './pdfjs'

/**
 * pdf.js 的 `rotation` 是**覆盖**页自身 `/Rotate`（`getViewport` 的默认值就是
 * `page.rotate`），所以要「在原有方向上再转」必须自己相加；非 90 倍数会让
 * `PageViewport` 直接抛错，这里统一收敛。
 */
function totalRotation(pageRotate: number | undefined, delta: number): number {
  const sum = Math.round(((Number(pageRotate) || 0) + (Number(delta) || 0)) / 90) * 90
  return ((sum % 360) + 360) % 360
}

/**
 * 把 PDF 的一页渲染到 canvas，返回画好的 canvas（未附加到 DOM）。
 *
 * ``rotation`` 是**在页自身 /Rotate 之上叠加的顺时针角度**（0/90/180/270）。
 * 90/270 时显示宽高互换，所以目标宽度按「旋转后的宽」反算缩放——否则横过来
 * 的页会渲染成一条窄带（位图宽按原宽算，显示时被 CSS 拉回目标宽，字就糊了）。
 */
export async function renderPdfPage(
  pdf: pdfjsLib.PDFDocumentProxy,
  pageNum: number,
  targetWidth = PDF_RENDER_WIDTH,
  rotation = 0,
): Promise<HTMLCanvasElement> {
  const page = await pdf.getPage(pageNum)
  const base = page.getViewport({ scale: 1 })
  const quarterTurn = totalRotation(page.rotate, rotation) % 180 !== 0
  const baseWidth = quarterTurn ? base.height : base.width
  const scale = targetWidth / baseWidth
  const viewport = page.getViewport({ scale, rotation: totalRotation(page.rotate, rotation) })
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

/**
 * 渲染 PDF 一页并裁出归一化矩形区域，返回画好的 canvas（四周留一点空白）。
 *
 * ``rect`` 是**旋转后坐标系**里的矩形（与用户在屏幕上框选的那块一致），
 * ``rotation`` 与 `renderPdfPage` 同义——两者必须一起传，否则裁出来的
 * 会是隔壁那一块。
 */
export async function renderPdfPageRegion(
  pdf: pdfjsLib.PDFDocumentProxy,
  pageNum: number,
  rect: NormRect,
  targetWidth = 1600,
  rotation = 0,
): Promise<HTMLCanvasElement> {
  const full = await renderPdfPage(pdf, pageNum, targetWidth, rotation)
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
