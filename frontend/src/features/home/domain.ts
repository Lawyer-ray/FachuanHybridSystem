/**
 * 首页纯领域逻辑：日期与月历网格的纯函数。
 *
 * 事件归一化 / 同一庭审合并 / 统计口径已移到后端
 * （GET /reminders/calendar，与 Django admin 日历共用同一个 service），
 * 前端不再自己合并或计数——否则两边口径会漂移。
 * 这里只保留与后端无关的日期计算，便于单测。
 */

/* ------------------------------------------------------------------ 日期工具 */

/** 补零 */
export function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

/** 本地时区的 YYYY-MM-DD（不能用 toISOString，那是 UTC，东八区会差一天） */
export function dateKey(d: Date): string {
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

/** 今天（本地）的 dateKey */
export function todayKey(now: Date = new Date()): string {
  return dateKey(now)
}

/** 把 HH:mm 从 ISO 串中取出；没有时分则返回 '全天' */
export function timeOfDay(iso: string): string {
  const m = /T(\d{2}):(\d{2})/.exec(iso)
  return m ? `${m[1]}:${m[2]}` : '全天'
}

/** YYYY-MM-DD → 本地 Date */
export function parseKey(key: string): Date {
  const [y, m, d] = key.split('-').map(Number)
  return new Date(y, m - 1, d)
}

/** 星期标题用：周一起点的月历网格里，日期 d 是第几列（0=周一） */
export function weekdayColumn(d: Date): number {
  return (d.getDay() + 6) % 7
}

/** 中文日期：'9 月 17 日' */
export function formatCN(d: Date): string {
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日`
}

/** 中文星期：'周四' */
export function formatWeekdayCN(d: Date): string {
  return ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][d.getDay()]
}

/* ------------------------------------------------------------------ 日历网格 */

export interface DayCell {
  /** dateKey；null 表示占位格（上/下月补白） */
  key: string | null
  day: number | null
  /** 是否当月 */
  inMonth: boolean
}

/**
 * 生成某月的周一起点日历网格。
 *
 * 行数按实际需要算（首行补白 + 当月天数，向上取整到整周），不固定 6 行：
 * 2026 年 12 个月里有 9 个月只需 5 行，固定 6 行等于大多数时间都多渲染
 * 一整行下月空白格。
 */
export function buildMonthGrid(year: number, month: number): DayCell[] {
  const first = new Date(year, month, 1)
  const lead = weekdayColumn(first)
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const rows = Math.ceil((lead + daysInMonth) / 7)
  const cells: DayCell[] = []
  // 上月补白
  const prevDays = new Date(year, month, 0).getDate()
  for (let i = lead - 1; i >= 0; i--) {
    cells.push({ key: dateKey(new Date(year, month - 1, prevDays - i)), day: prevDays - i, inMonth: false })
  }
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push({ key: dateKey(new Date(year, month, d)), day: d, inMonth: true })
  }
  // 下月补白到整周（只补到最后一行结束，不再多补一行）
  let next = 1
  while (cells.length < rows * 7) {
    cells.push({ key: dateKey(new Date(year, month + 1, next)), day: next, inMonth: false })
    next += 1
  }
  return cells
}
