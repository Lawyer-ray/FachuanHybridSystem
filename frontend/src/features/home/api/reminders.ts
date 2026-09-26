import { createApiClient } from '@/lib/api'

/** 日程 / 庭期提醒资源（/api/v1/reminders）。 */

export const remindersApi = createApiClient({ prefix: '/api/v1/reminders' })

/** 日历上的一条事件（GET /reminders/calendar）。同一庭审的多条同步已由后端合并。 */
export interface CalendarEvent {
  id: number
  kind: string
  kind_label: string
  /** 主标题：后端优先取关联对象名，取不到才退回 content */
  title: string
  /** content 原文 */
  content: string
  day: string
  time: string
  time_range: string
  place: string
  person: string
  /** 真实案号（后端取自案件的 CaseNumber），如 （2026）粤0608民初8233号 */
  case_no: string
  hearing_type: string
  target_type: string
  target_name: string
  case_id: number | null
  is_today: boolean
  is_overdue: boolean
  /** 合并了几条原始 reminder（同一庭审被多次同步时 >1） */
  members: number
  member_ids: number[]
}

/** 工作台统计（后端按合并后口径算好，前端不要再自己数） */
export interface CalendarStats {
  today: number
  deadline_in_7days: number
  month_court: number
}

/** GET /reminders/calendar 的响应 */
export interface CalendarMonth {
  year: number
  month: number
  stats: CalendarStats
  /** YYYY-MM-DD → 当日事件（已合并、已排序） */
  days: Record<string, CalendarEvent[]>
}

/**
 * 取某月日历视图。合并、归一化、统计都在后端做——
 * 首页与 Django admin 日历共用同一个 service，避免两边口径不一致。
 */
export async function fetchCalendarMonth(year: number, month: number): Promise<CalendarMonth> {
  return remindersApi
    .get('calendar', { searchParams: { year, month } })
    .json<CalendarMonth>()
}

/** 关联对象类型（提醒可绑定 合同 / 案件 / 案件日志 三选一） */
export type TargetType = 'contract' | 'case' | 'case_log'

/**
 * 关联对象候选项（GET /reminders/target-options）。
 *
 * 后端 name 字段是**给 admin 的组合标签**，格式不统一：
 *   - contract / case：`案件或合同名`
 *   - case_log：`#{id} {案件名}｜{日志摘要}`（见 target_query.py:48）
 * searchTargetOptions 会把它拆成 title / hint 两个字段，前端按各自版式排版。
 * 不改后端——那个标签格式 admin 也在用。
 */
export interface TargetOption {
  id: number
  target_type: TargetType
  target_type_label: string
  /** 主展示名：案件名 / 合同名（已去掉 `#id` 前缀） */
  title: string
  /** 次级说明：案件日志的内容摘要，其它类型为空 */
  hint: string
}

/** wire 上的原始字段 */
interface RawTargetOption {
  id: number
  name: string
  target_type: TargetType
  target_type_label: string
}

/** 后端原始 name 标签 → title + hint */
function splitTargetName(targetType: TargetType, rawName: string): { title: string; hint: string } {
  const name = rawName.trim()
  if (targetType !== 'case_log') return { title: name, hint: '' }
  // case_log：「#123 案件名｜日志摘要」→ 丢掉 `#id ` 前缀，再按｜拆开
  const withoutId = /^#\d+\s+(.*)$/.exec(name)?.[1] ?? name
  const sep = withoutId.indexOf('｜')
  if (sep < 0) return { title: withoutId, hint: '' }
  return { title: withoutId.slice(0, sep).trim(), hint: withoutId.slice(sep + 1).trim() }
}

/**
 * 按关键字联想关联对象（合同 / 案件 / 案件日志）。
 * 与 admin 提醒日历用的是同一个接口，返回已拆好 title/hint 的结果。
 */
export async function searchTargetOptions(q: string): Promise<TargetOption[]> {
  const res = await remindersApi.get('target-options', { searchParams: { q } }).json<{ items?: RawTargetOption[] }>()
  return (res.items ?? []).map((raw) => {
    const { title, hint } = splitTargetName(raw.target_type, raw.name ?? '')
    return {
      id: raw.id,
      target_type: raw.target_type,
      target_type_label: raw.target_type_label,
      title,
      hint,
    }
  })
}

/** 提醒类型选项（GET /reminders/types），用于新增安排弹窗的下拉 */
export interface ReminderTypeOption {
  value: string
  label: string
}

export async function listReminderTypes(): Promise<ReminderTypeOption[]> {
  return remindersApi.get('types').json<ReminderTypeOption[]>()
}

export interface ParsedReminder {
  content: string
  reminder_type: string
  reminder_type_label: string
  due_at: string
  source_text: string
}

/**
 * 用文本解析提醒。后端是规则抽取而非 LLM：需要显式日期（如「2026-09-28 09:30 …」）
 * 才能识别，相对时间（「明天」「下周五」）会返回空数组。
 */
export async function parseReminder(text: string): Promise<ParsedReminder[]> {
  const res = await remindersApi.post('parse', { json: { text } }).json<ParsedReminder[]>()
  return res ?? []
}

export interface CreateReminderIn {
  reminder_type: string
  content: string
  /** ISO 字符串，如 2026-09-28T09:30:00 */
  due_at: string
  /**
   * 关联对象。后端 ReminderIn 用 contract_id / case_id / case_log_id
   * 三个独立字段，且三者最多绑一个（模型上有 CheckConstraint）。
   * 这里统一用 target_type + target_id 表达，发送时再拆开。
   */
  target_type?: TargetType | null
  target_id?: number | null
}

export async function createReminder(payload: CreateReminderIn): Promise<void> {
  const field = {
    contract: 'contract_id',
    case: 'case_id',
    case_log: 'case_log_id',
  }[String(payload.target_type)] as string | undefined
  await remindersApi.post('create', {
    json: {
      reminder_type: payload.reminder_type,
      content: payload.content,
      due_at: payload.due_at,
      // 只填对应的那一个 id，其余保持缺省（后端要求三者最多一个）
      [field || 'case_id']: payload.target_type ? (payload.target_id ?? null) : null,
    },
  })
}
