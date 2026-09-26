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

/** 一条提醒里日历视图要用的字段（从 ReminderOut 抽出，便于合并） */
interface RawEvent {
  id: string
  day: string
  kind: EventKind
  time: string
  title: string
  /** 法庭 / 地点 */
  place: string
  /** 时段（如 10:00-12:00），来自 metadata.time_range */
  timeRange: string
  /** 承办法官或代理律师 */
  person: string
  /** 案号 */
  caseNo: string
  /** 庭审方式（线下开庭 / 网上开庭等） */
  hearingType: string
  caseId: number | null
  dueToday: boolean
  /** 关联对象描述（案件/合同名） */
  targetName: string
  /** 合并用键：同一庭审的多条同步记录共享 */
  mergeKey: string
}

/**
 * Reminder → RawEvent（尚未合并）。
 * 庭审类按 metadata.source_id 生成合并键：一张网庭审日程会为每位代理律师
 * 各同步一条提醒（同案号、同时间、同法庭），不合并就会在日历上重复展示。
 * 无 source_id 时退化为「同日同时刻同标题同地点」合并，和 admin 口径一致。
 */
function toRawEvent(r: ReminderOut, today: string): RawEvent {
  const kind: EventKind = KIND_BY_REMINDER_TYPE[r.reminder_type] ?? 'follow'
  const meta = r.metadata ?? {}
  const day = dateKey(new Date(r.due_at))
  const time = timeOfDay(r.due_at)

  const courtroom = metaStr(meta, 'courtroom')
  const location = metaStr(meta, 'location')
  const place = courtroom || location
  const person = metaStr(meta, 'lawyer_name') || metaStr(meta, 'judge_name')
  const caseNo = metaStr(meta, 'ajbs') || metaStr(meta, 'ah') || metaStr(meta, 'case_no')
  const timeRange = metaStr(meta, 'time_range')

  // 注意：/reminders/list 只给关联对象 id（case/contract/case_log 都是数字），
  // 拿不到名称（admin 是服务端 select_related 直接带出）。要展示案名得后端
  // 在列表接口里补字段，这里先留空。
  const targetName = ''

  let mergeKey = ''
  if (kind === 'court') {
    // 庭审合并键。真实数据里同一个庭会以多种形态重复同步，观察到的三种情况：
    //
    //   1) source_id 相同（同一次同步，每位律师各存一条）
    //        → 合并，律师姓名聚合成「房长波、黄崧」
    //   2) source_id / ajbs / 案名都不同，但「同日 + 同时刻 + 同法庭」
    //        → 仍是同一个庭（一张网按律师分别落案，案号相邻、案名长短不一）。
    //          实测 2026-09-09：4 条记录、2 个案号、2 种案名，其实是 1 个庭。
    //   3) 手工录入、metadata 为空 → 无从判断，不合并
    //
    // 键只用「日 + 时段 + 法庭」：案名在情况 2 里不可靠（同庭两个案号的案名
    // 不一致），法庭才是稳定标识。也**不能**用 source_id 做主键——情况 2 的
    // source_id 本来就不同。
    // 用 time_range 兜时间：有些庭审 due_at 是同步时刻而非开庭时刻。
    //
    // 没有法庭信息时**不合并**：否则同一天同时刻的所有手工庭会被并成一条
    // （比如两个不同案子都只写了「9:00 开庭」）。
    if (place) {
      mergeKey = `hearing:${day} ${timeRange || time} ${place}`
    }
  }

  return {
    id: String(r.id),
    day,
    kind,
    time,
    title: r.content,
    place,
    timeRange,
    person,
    caseNo,
    hearingType: metaStr(meta, 'hearing_type'),
    caseId: r.case ?? null,
    dueToday: day === today,
    targetName,
    mergeKey,
  }
}

/**
 * 合并同一庭审的多条同步记录：保留首条的展示字段，律师姓名用「、」聚合去重。
 * 与 admin 的 _group_events_by_day 合并逻辑对齐。
 */
function mergeSameHearing(events: RawEvent[]): RawEvent[] {
  const seen = new Map<string, RawEvent>()
  const persons = new Map<string, string[]>()
  const out: RawEvent[] = []

  for (const e of events) {
    if (!e.mergeKey) {
      out.push(e)
      continue
    }
    const hit = seen.get(e.mergeKey)
    if (!hit) {
      seen.set(e.mergeKey, e)
      if (e.person) persons.set(e.mergeKey, [e.person])
      out.push(e)
      continue
    }
    // 已存在：聚合律师姓名（保持出现顺序、去重）
    if (e.person) {
      const list = persons.get(e.mergeKey) ?? []
      if (!list.includes(e.person)) list.push(e.person)
      persons.set(e.mergeKey, list)
      hit.person = list.join('、')
    }
    // 补首条缺失的展示字段
    if (!hit.place && e.place) hit.place = e.place
    if (!hit.caseNo && e.caseNo) hit.caseNo = e.caseNo
    if (!hit.timeRange && e.timeRange) hit.timeRange = e.timeRange
    if (!hit.targetName && e.targetName) hit.targetName = e.targetName
    if (!hit.caseId && e.caseId) hit.caseId = e.caseId
  }
  return out
}

/**
 * 后端提醒列表 → 日历事件列表。
 * 先按需合并同一庭审的多条同步记录，再按「日期 + 时间」升序排（同日同时刻按 id 稳定排序）。
 */
export function toDayEvents(reminders: ReminderOut[], today: string): DayEvent[] {
  const merged = mergeSameHearing(reminders.map((r) => toRawEvent(r, today)))
  return merged
    .map((e) => ({
      id: e.id,
      day: e.day,
      kind: e.kind,
      time: e.time,
      title: e.title,
      place: e.place,
      timeRange: e.timeRange,
      person: e.person,
      caseNo: e.caseNo,
      hearingType: e.hearingType,
      caseId: e.caseId,
      dueToday: e.dueToday,
      targetName: e.targetName,
    }))
    .sort((a, b) => (a.day === b.day ? a.time.localeCompare(b.time) || a.id.localeCompare(b.id) : a.day < b.day ? -1 : 1))
}

/**
 * 事件的副标题摘要。优先级与 admin 的 reminder-event-meta 一致：
 * 有人名/地点时给「人名 · 地点」，否则退到案号 / 关联对象名。
 */
export function summaryLine(e: DayEvent): string {
  const parts = [e.person, e.place].filter(Boolean)
  if (parts.length) return parts.join(' · ')
  const fallback = [e.caseNo, e.targetName].filter(Boolean)
  return fallback.join(' · ')
}

/** 日历格子 / 右栏里更紧凑的一行：只留最关键的一段（地点优先，其次人名） */
export function briefLine(e: DayEvent): string {
  return e.place || e.person || e.caseNo || e.targetName
}

/** 时段区间（若与开始时刻相同则不加，避免「10:00 · 10:00-12:00」这种废话） */
export function rangeLabel(e: DayEvent): string {
  if (!e.timeRange) return ''
  const start = e.timeRange.split('-')[0]
  return start === e.time ? e.timeRange : e.timeRange
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
