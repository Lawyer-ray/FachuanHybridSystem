/**
 * 日历密度档 —— 一律按**面板净宽**判定，不看视口。
 *
 * 为什么必须按净宽：AI 助手并排让位（AppShell 的 padding-right）与分屏窗口会
 * 把日历面板压到几百像素，而视口依旧很宽。此时 `max-[760px]:` 与
 * `useMediaQuery('(max-width: 760px)')` 都不成立，日历仍按桌面渲染「时间 + 标题 +
 * 关联对象 + 律师 + 地点」五行卡片，塞进 40~90px 宽的格子里，每行只剩 1~2 个字
 * （实测 664px 面板下每张卡片都是「佛...」「梁. 房... 佛...」），完全不可读。
 * 面板宽窄只有 ResizeObserver 量得到，故档位在这里集中定义，组件只消费档名。
 */

/** 格子内容密度：wide=五行卡片，medium=两行卡片，compact=圆点 + 标题（点格开当日抽屉） */
export type CalendarDensity = 'wide' | 'medium' | 'compact'

/** 面板净宽 < 此值 → compact。680 ≈ 7 格 × 97px：低于此宽度连「时间 + 标题」都放不下 */
export const COMPACT_BELOW = 680

/**
 * 面板净宽 < 此值 → medium（两行卡片）。900 ≈ 7 格 × 126px：再窄下去五行卡片每行
 * 只剩七八个字，塞的是地点/律师这种可从详情里看的次要信息。
 * 900 以上保持原有的五行卡片（1440/1512 笔电整宽、助手未并排时都在这一档，不动手感）。
 */
export const MEDIUM_BELOW = 900

/**
 * 面板净宽 → 密度档。
 * @param width  面板实测净宽；0 表示还没量到（首帧 / jsdom 无布局）
 * @param fallback 量不到宽时用哪一档（手机视口给 compact，其余给 wide）
 */
export function densityForWidth(width: number, fallback: CalendarDensity): CalendarDensity {
  if (!Number.isFinite(width) || width <= 0) return fallback
  if (width < COMPACT_BELOW) return 'compact'
  if (width < MEDIUM_BELOW) return 'medium'
  return 'wide'
}

/**
 * 每格最多放几个事件行（超出折叠成「+N 更多」）。
 * 阈值由旧视口断点 2400/1600 扣除页边距与右栏换算而来，同样是面板净宽口径。
 */
export function maxRowsForWidth(width: number): number {
  if (width >= 1900) return 5
  if (width >= 1150) return 4
  return 3
}
