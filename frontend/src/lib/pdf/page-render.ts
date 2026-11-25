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

/**
 * 把图片字节裁出归一化矩形区域，返回 PNG Blob。
 *
 * ``rotation`` 是人工转正角度（顺时针）。图片素材没有 `/Rotate` 可读，所以这里
 * 先把整张图按角度画到一张临时画布上，再按同一坐标系裁剪——`rect` 是**屏幕上
 * 画的**（旋转后）坐标，不先转就裁会截到隔壁那块（同 `renderPdfPageRegion`）。
 */
export async function imageRegionBlob(bytes: ArrayBuffer, rect: NormRect, rotation = 0): Promise<Blob> {
  const url = URL.createObjectURL(new Blob([bytes]))
  try {
    const img = new Image()
    await new Promise<void>((res, rej) => {
      img.onload = () => res()
      img.onerror = () => rej(new Error('图片解码失败'))
      img.src = url
    })
    const source = rotateImageToCanvas(img, img.width, img.height, rotation)
    const pad = 0.02
    const cw = Math.max(32, Math.round(source.width * rect.w))
    const ch = Math.max(32, Math.round(source.height * rect.h))
    const canvas = document.createElement('canvas')
    canvas.width = Math.min(source.width, cw + Math.round(source.width * pad * 2))
    canvas.height = Math.min(source.height, ch + Math.round(source.height * pad * 2))
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('无法创建 canvas 2d 上下文')
    ctx.fillStyle = '#ffffff'
    ctx.fillRect(0, 0, canvas.width, canvas.height)
    const sx = Math.max(0, source.width * rect.x - Math.round(source.width * pad))
    const sy = Math.max(0, source.height * rect.y - Math.round(source.height * pad))
    ctx.drawImage(source, sx, sy, canvas.width, canvas.height, 0, 0, canvas.width, canvas.height)
    return await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('PNG 编码失败'))), 'image/png')
    })
  } finally {
    URL.revokeObjectURL(url)
  }
}

/** 把位图画成一张按角度转好的画布；0° 时直接返回原尺寸的新画布（调用方统一走这里） */
function rotateImageToCanvas(source: CanvasImageSource, width: number, height: number, rotation: number): HTMLCanvasElement {
  const swapped = rotation === 90 || rotation === 270
  const canvas = document.createElement('canvas')
  canvas.width = swapped ? height : width
  canvas.height = swapped ? width : height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('无法创建 canvas 2d 上下文')
  if (rotation === 0) {
    // 0° 直接画：不必走矩阵（也少一次与 canvas 实现的耦合）
    ctx.drawImage(source, 0, 0, width, height)
    return canvas
  }
  ctx.translate(canvas.width / 2, canvas.height / 2)
  ctx.rotate((rotation * Math.PI) / 180)
  ctx.drawImage(source, -width / 2, -height / 2)
  return canvas
}

/** 把 canvas 编码成 PNG Blob */
export function canvasToBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('PNG 编码失败'))), 'image/png')
  })
}
