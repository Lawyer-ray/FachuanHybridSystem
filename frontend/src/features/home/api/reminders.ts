import { createApiClient } from '@/lib/api'
import type { components, operations } from '@/types/api-schema'

/** 日程 / 庭期提醒资源（/api/v1/reminders）。 */

export const remindersApi = createApiClient({ prefix: '/api/v1/reminders' })

/**
 * 日历上的一条事件（GET /reminders/calendar 的行，生成物 CalendarEventItemOut）。
 * 同一庭审的多条同步已由后端合并。
 * 注意：生成物里 member_ids / case_id 为可选——member_ids 消费处按 `?? []` 兜底
 * （domain.ts 的 eventReminderIds 已如此），合并语义以后端为准。 */
export type CalendarEvent = components['schemas']['CalendarEventItemOut']

/** 工作台统计（生成物 CalendarStatsOut；后端按合并后口径算好，前端不要再自己数）。
 *  today / deadline_in_7days 是紧急度指标，只数未完成；month_court 保持全量。 */
export type CalendarStats = components['schemas']['CalendarStatsOut']

/** GET /reminders/calendar 的响应（按 operationId 取生成物） */
export type CalendarMonth = operations['apps_reminders_api_reminder_api_get_calendar_month']['responses'][200]['content']['application/json']

/**
 * 取某月日历视图。合并、归一化、统计都在后端做——
 * 首页与 Django admin 日历共用同一个 service，避免两边口径不一致。
 */
export async function fetchCalendarMonth(year: number, month: number): Promise<CalendarMonth> {
  return remindersApi
    .get('calendar', { searchParams: { year, month } })
    .json<CalendarMonth>()
}

/**
 * 批量标记完成 / 取消完成（生成物 ReminderCompleteOut = 实际更新条数）。
 * 合并事件的全部 member_ids 必须一起传
 * （用 domain.ts 的 eventReminderIds 取），否则下次合并回显未完成。
 */
export async function setRemindersCompleted(reminderIds: number[], isCompleted: boolean): Promise<number> {
  const res = await remindersApi
    .post('complete', { json: { reminder_ids: reminderIds, is_completed: isCompleted } })
    .json<components['schemas']['ReminderCompleteOut']>()
  return res.updated
}

/** 日历 query key 工厂：跨文件 invalidate / 订阅都从这里取，避免裸字符串漂移 */
export const calendarKeys = {
  all: ['home-calendar'] as const,
  month: (year: number, month: number) => ['home-calendar', year, month] as const,
}

/** 提醒类型下拉的 query key（AddReminderDialog 用） */
export const REMINDER_TYPES_KEY = ['reminder-types'] as const

/** 关联对象类型（提醒可绑定 合同 / 案件 / 案件日志 三选一） */
export type TargetType = 'contract' | 'case' | 'case_log'

/** TargetType 白名单：target-options 响应里 target_type 生成物是裸 string，
 *  收窄前先过白名单，未知值不进类型系统 */
const TARGET_TYPES = ['contract', 'case', 'case_log'] as const

function isTargetType(v: string): v is TargetType {
  return (TARGET_TYPES as readonly string[]).includes(v)
}

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
 * 与 admin 提醒日历用的是同一个接口（生成物 TargetOptionsOut），返回已拆好 title/hint 的结果。
 */
export async function searchTargetOptions(q: string, signal?: AbortSignal): Promise<TargetOption[]> {
  const res = await remindersApi
    .get('target-options', { searchParams: { q }, signal })
    .json<components['schemas']['TargetOptionsOut']>()
  return (res.items ?? []).map((raw) => {
    // 生成物把 target_type 声明为裸 string；白名单校验后收窄，非法值兜底为
    // 'contract'（关联对象仅影响新增弹窗的预填，兜底不丢整条候选）
    const targetType = isTargetType(raw.target_type) ? raw.target_type : 'contract'
    const { title, hint } = splitTargetName(targetType, raw.name ?? '')
    return {
      id: raw.id,
      target_type: targetType,
      target_type_label: raw.target_type_label,
      title,
      hint,
    }
  })
}

/** 提醒类型选项（GET /reminders/types 的行，生成物 ReminderTypeItem），用于新增安排弹窗的下拉 */
export type ReminderTypeOption = components['schemas']['ReminderTypeItem']

export async function listReminderTypes(): Promise<ReminderTypeOption[]> {
  return remindersApi.get('types').json<ReminderTypeOption[]>()
}

/** POST /reminders/parse 的响应行（生成物 ParsedReminderOut） */
export type ParsedReminder = components['schemas']['ParsedReminderOut']

/**
 * 用文本解析提醒。后端是规则抽取而非 LLM：需要显式日期（如「2026-09-28 09:30 …」）
 * 才能识别，相对时间（「明天」「下周五」）会返回空数组。
 */
export async function parseReminder(text: string): Promise<ParsedReminder[]> {
  const res = await remindersApi.post('parse', { json: { text } }).json<ParsedReminder[]>()
  return res ?? []
}

/**
 * 手写保留：新建安排的前端入参形状（target_type + target_id 统一表达），
 * 与 wire 上的 ReminderIn（contract_id / case_id / case_log_id 三字段）不同，
 * 发送时在 createReminder 内拆开，故不能直接引用生成物。
 */
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
  // Record<TargetType, ...> 让三个 key 必须穷举，拼错编译期就报
  const fieldByTarget: Record<TargetType, 'contract_id' | 'case_id' | 'case_log_id'> = {
    contract: 'contract_id',
    case: 'case_id',
    case_log: 'case_log_id',
  }
  const field = payload.target_type ? fieldByTarget[payload.target_type] : undefined
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
