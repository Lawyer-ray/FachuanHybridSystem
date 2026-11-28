import { casesApi, remindersApi } from './client'

/**
 * 「期限」与「项目日志」两条写接口（详情页的「＋ 新增 / ＋ 记日志」）。
 *
 * 两件事在后端是**一张表的两面**：`POST /cases/logs` 可以在创建日志的同时挂一条
 * 提醒（`reminder_type` + `reminder_time`），`POST /reminders/create` 则可以直接
 * 把提醒挂到合同或案件上。前端按律师的意图分成两个入口，不去模拟第三种写法。
 */

/** 提醒类型选项（GET /reminders/types） */
export interface ReminderTypeOption {
  value: string
  label: string
}

export async function listReminderTypes(): Promise<ReminderTypeOption[]> {
  return remindersApi.get('types').json<ReminderTypeOption[]>()
}

/**
 * 建一条期限。
 *
 * 后端 `ReminderIn` 用 contract_id / case_id / case_log_id 三个独立字段，且三者
 * 最多绑一个（模型 CheckConstraint）——所以这里按「挂委托」或「挂案件」二选一，
 * 只填对应的那一个，其余整键不发（发了 null 也算一次显式绑定尝试）。
 */
export async function createReminder(input: {
  reminderType: string
  content: string
  /** 本地时间 `YYYY-MM-DDTHH:mm:00`（不带时区，Django 按当前时区解释） */
  dueAt: string
  /** 挂到委托（合同直挂）；与 caseId 互斥 */
  contractId?: number
  /** 挂到具体案件；与 contractId 互斥 */
  caseId?: number
}): Promise<void> {
  await remindersApi.post('create', {
    json: {
      reminder_type: input.reminderType,
      content: input.content,
      due_at: input.dueAt,
      ...(input.caseId != null ? { case_id: input.caseId } : {}),
      ...(input.contractId != null ? { contract_id: input.contractId } : {}),
    },
  })
}

/**
 * 记一条项目日志（归属必须是**具体案件**：合同没有日志，时间轴长在案件上）。
 *
 * `reminder_type` + `reminder_time` 同时给，后端会在建日志的同时挂一条提醒——
 * 「记一笔 + 约个跟进」是律师写日志时最常见的组合，分成两次操作反而容易漏。
 */
export async function createCaseLog(input: {
  caseId: number
  content: string
  reminderType?: string
  /** 与 createReminder 同口径的本地时间串 */
  reminderTime?: string
}): Promise<{ id?: number }> {
  return casesApi
    .post('logs', {
      json: {
        case_id: input.caseId,
        content: input.content,
        ...(input.reminderType && input.reminderTime
          ? { reminder_type: input.reminderType, reminder_time: input.reminderTime }
          : {}),
      },
    })
    .json<{ id?: number }>()
}
