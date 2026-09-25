/**
 * 首页纯领域逻辑：把后端 Reminder 归一化成日历事件、按日归集、算统计。
 * 全部为不可变纯函数，便于单测（不碰 React、不碰网络）。
 */

import { KIND_BY_REMINDER_TYPE, isKeyKind } from './constants'
import type { DayEvent, EventKind } from './types'
import type { ReminderOut } from './api'

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
 * 生成某月的周一起点日历网格（固定 6 行 42 格，保持布局不跳动）。
 */
export function buildMonthGrid(year: number, month: number): DayCell[] {
  const first = new Date(year, month, 1)
  const lead = weekdayColumn(first)
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const cells: DayCell[] = []
  // 上月补白
  const prevDays = new Date(year, month, 0).getDate()
  for (let i = lead - 1; i >= 0; i--) {
    cells.push({ key: dateKey(new Date(year, month - 1, prevDays - i)), day: prevDays - i, inMonth: false })
  }
  for (let d = 1; d <= daysInMonth; d++) {
    cells.push({ key: dateKey(new Date(year, month, d)), day: d, inMonth: true })
  }
  // 下月补白到 42 格
  let next = 1
  while (cells.length < 42) {
    cells.push({ key: dateKey(new Date(year, month + 1, next)), day: next, inMonth: false })
    next += 1
  }
  return cells
}

/* ------------------------------------------------------------------ 事件归一化 */

/** 取 metadata 里的字符串字段 */
function metaStr(meta: Record<string, unknown>, key: string): string {
  const v = meta[key]
  return typeof v === 'string' && v.trim() ? v.trim() : ''
}

/**
 * Reminder → DayEvent。
 * 副标题优先用 metadata 里的案号/法庭/当事人信息，退化为空。
 */
export function toDayEvent(r: ReminderOut, today: string): DayEvent {
  const kind: EventKind = KIND_BY_REMINDER_TYPE[r.reminder_type] ?? 'follow'
  const meta = r.metadata ?? {}
  const day = dateKey(new Date(r.due_at))
  const subtitleParts = [
    metaStr(meta, 'courtroom'),
    metaStr(meta, 'ajbs'),
    metaStr(meta, 'party'),
    metaStr(meta, 'case_no'),
    metaStr(meta, 'ah'),
  ].filter(Boolean)
  return {
    id: String(r.id),
    day,
    kind,
    time: timeOfDay(r.due_at),
    title: r.content,
    subtitle: subtitleParts.join(' · '),
    reminderType: r.reminder_type,
    caseId: r.case ?? null,
    dueToday: day === today,
  }
}

/** 后端提醒列表 → 日历事件列表（按时间升序） */
export function toDayEvents(reminders: ReminderOut[], today: string): DayEvent[] {
  return reminders
    .map((r) => toDayEvent(r, today))
    .sort((a, b) => (a.day === b.day ? a.time.localeCompare(b.time) : a.day < b.day ? -1 : 1))
}

/** 按 dateKey 归集成日历；同一天内按时间升序，紧要事项排前 */
export function groupByDay(events: DayEvent[]): Map<string, DayEvent[]> {
  const map = new Map<string, DayEvent[]>()
  for (const e of events) {
    const list = map.get(e.day)
    if (list) list.push(e)
    else map.set(e.day, [e])
  }
  for (const list of map.values()) {
    list.sort((a, b) => {
      if (isKeyKind(a.kind) !== isKeyKind(b.kind)) return isKeyKind(a.kind) ? -1 : 1
      return a.time.localeCompare(b.time)
    })
  }
  return map
}

/* ------------------------------------------------------------------ 统计 */

export interface DeskStats {
  todayCount: number
  /** 7 日内（含今天）到期的紧要事项数 */
  deadlineIn7: number
  /** 本月庭期数 */
  courtThisMonth: number
}

/**
 * 工作台统计。口径与原型一致：
 *   今日 = 今天的事件条数
 *   7 日内到期 = [today, today+6] 内到期的「紧要」事项（庭期/期限）
 *   本月庭期 = 与 today 同年的同月里 kind === court 的条数
 */
export function computeStats(events: DayEvent[], today: string): DeskStats {
  const todayDate = parseKey(today)
  const limit = new Date(todayDate)
  limit.setDate(limit.getDate() + 6)
  const limitKey = dateKey(limit)
  let todayCount = 0
  let deadlineIn7 = 0
  let courtThisMonth = 0
  for (const e of events) {
    if (e.day === today) todayCount += 1
    if (isKeyKind(e.kind) && e.day >= today && e.day <= limitKey) deadlineIn7 += 1
    if (e.kind === 'court' && e.day.startsWith(today.slice(0, 7))) courtThisMonth += 1
  }
  return { todayCount, deadlineIn7, courtThisMonth }
}

/** YYYY-MM-DD → 本地 Date */
export function parseKey(key: string): Date {
  const [y, m, d] = key.split('-').map(Number)
  return new Date(y, m - 1, d)
}
