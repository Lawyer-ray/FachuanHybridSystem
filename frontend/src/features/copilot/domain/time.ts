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

/**
 * 会话列表行的时间戳（`MM-DD HH:MM`）：跨天回溯时要看日期，当年的会话不必带年份。
 *
 * 直接切 ISO 字符串而**不过 Date**：后端的 `updated_at` 形如
 * `2026-11-20T09:05:30.123+08:00`，时区偏移与毫秒都在第 19 位之后，`MM-DD HH:MM`
 * 恒落在下标 5..16。走 Date 会把它换算成浏览器本地时区——列表里一排时间戳会与
 * 详情页/导出里的绝对时刻对不上，而这里要的就是服务端记下的那一刻。
 */
export function formatSessionStamp(iso: string): string {
  return iso.replace('T', ' ').slice(5, 16)
}
