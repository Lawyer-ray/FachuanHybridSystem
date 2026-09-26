/**
 * 阅读器多列布局的常量与纯计算。
 * Reader 与 Flow 共用同一份口径，避免「依赖子组件拿常量」的倒挂与两处各算一遍导致漂移。
 */

/** 原型多列模型参数：
 *  100% = 适应宽度，页宽 = min(960, 可用均分)；
 *  每列至少 COL_MIN_W 才有资格并排；缩放用倍率乘在页宽上（非 CSS zoom）。 */
export const COL_GAP = 18
export const PAGE_MAX_W = 960
export const COL_MIN_W = 360
export const PAGE_MIN_W = 140

/** 当前容器宽度下最多能并排几列（每列至少 COL_MIN_W）。 */
export function maxColsAllowed(width: number): number {
  return Math.max(1, Math.floor((width + COL_GAP) / (COL_MIN_W + COL_GAP)))
}

/**
 * 计算某列的页宽（px）。floor 而非 round：保证页行宽度 ≤ 画布宽，
 * 100% 缩放下不越界、恒居中；仅当缩放 >100% 时行宽才会超画布，允许横向滚动。
 */
export function fitPageWidth(width: number, nCols: number, zoom: number): number {
  const fit = Math.min(PAGE_MAX_W, (width - (nCols - 1) * COL_GAP) / nCols)
  return Math.max(PAGE_MIN_W, Math.floor(fit * zoom))
}

/** 整行页流的宽度（含列间距），用于判断是否超画布（zwide）。 */
export function rowWidth(pageW: number, nCols: number): number {
  return nCols * pageW + (nCols - 1) * COL_GAP
}
