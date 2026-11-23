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
