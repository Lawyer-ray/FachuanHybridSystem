/**
 * 时间显示（纯函数）。
 *
 * 转录里只需要「这条是几点说的」——律师回溯时问的是「上周三我问的那句」，
 * 而不是精确到毫秒的时间戳。完整时刻放 `title`，一眼看到的只给 HH:mm。
 */

/** 时刻（ms）→ `HH:mm`；无值返回空串（调用方据此不渲染） */
export function formatClock(ms?: number | null): string {
  if (!ms || !Number.isFinite(ms)) return ''
  const d = new Date(ms)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}
