/**
 * 首页 · 今日工作台数据模型。
 *
 * 事件（日程/庭期/期限）以「某一天 → 若干条安排」组织，底层来自后端 Reminder
 * （/reminders/list）：每条提醒有 reminder_type + due_at（ISO 时间）+ content，
 * 庭期类还在 metadata 里带 court/时间区间/案号等。这里的 DayEvent 是前端展示态：
 * 从 Reminder 归一化而来，便于日历直接按日期取用。
 */

/** 安排类别。前两类为「紧要」，其余为「常规」——对应原型图例的红/灰两色 */
export type EventKind = 'court' | 'deadline' | 'meeting' | 'follow'

/** 日历上的一天安排（由 Reminder 归一化） */
export interface DayEvent {
  /** 稳定 key：reminder id（同一来源去重/勾选用） */
  id: string
  /** 归属日期 YYYY-MM-DD（本地），由 due_at 换算 */
  day: string
  kind: EventKind
  /** HH:mm，来自 due_at；没有具体时分则给全天占位 */
  time: string
  title: string
  /** 副标题：案件/当事人/案号等摘要 */
  subtitle: string
  /** 原始 reminder 类型值，用于跳到详情/编辑 */
  reminderType: string
  /** 关联案件 id（有则可跳案件） */
  caseId: number | null
  /** 是否今天截止（用于强调） */
  dueToday: boolean
}

/** 待处理流入项（来自收件箱 /inbox/messages） */
export interface InboxItem {
  id: number
  kind: 'sms' | 'mat' | 'mail'
  sourceLabel: string
  who: string
  title: string
  at: string
  status: string
  action: string
  /** 是否紧急（法院短信）——用于图标与状态的红色强调 */
  hot: boolean
}

/** 快捷工具：要素式转换的文书模板项 */
export interface ConvertTemplate {
  mbid: string
  name: string
}

/** LPR 计算结果（/lpr/calculate 的响应节选） */
export interface LprResult {
  success: boolean
  totalInterest: string
  totalDays: number | null
  startDate: string | null
  endDate: string | null
  message: string | null
  /** 分档明细概要：如「3.10% × 19 天」 */
  summary: string
}
