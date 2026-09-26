import type { EventKind } from './types'

/**
 * 后端 ReminderType → 前端展示类别。
 * 后端的 8 种提醒（/reminders/types）归到原型的 4 类：
 *   court/deadline = 紧要（红），meeting/follow = 常规（灰）
 */
export const KIND_BY_REMINDER_TYPE: Record<string, EventKind> = {
  hearing: 'court',
  asset_preservation_expires: 'deadline',
  evidence_deadline: 'deadline',
  appeal_deadline: 'deadline',
  statute_limitations: 'deadline',
  payment_deadline: 'deadline',
  submission_deadline: 'deadline',
  other: 'follow',
}

/** 类别中文名（用于徽章与抽屉） */
export const KIND_LABEL: Record<EventKind, string> = {
  court: '庭期',
  deadline: '期限',
  meeting: '日程',
  follow: '跟进',
}

/** 类别 → tailwind 徽章类名（紧要=红，常规=灰） */
export const KIND_BADGE: Record<EventKind, string> = {
  court: 'border-status-red/30 bg-status-red-bg text-status-red',
  deadline: 'border-status-red/30 bg-status-red-bg text-status-red',
  meeting: 'border-border bg-secondary text-secondary-foreground',
  follow: 'border-border bg-secondary text-secondary-foreground',
}

/** 类别 → 日历事件行的 tailwind 类名 */
export const KIND_ROW: Record<EventKind, string> = {
  court: 'bg-status-red text-white',
  deadline: 'bg-status-red text-white',
  meeting: 'text-foreground',
  follow: 'text-foreground',
}

/** 是否紧要（用于图例、统计"今日件数"的红点、排序优先） */
export function isKeyKind(kind: EventKind): boolean {
  return kind === 'court' || kind === 'deadline'
}

/** 快捷工具展示用的端点注释（与后端真实路径一致，便于核对） */
export const TOOL_ENDPOINT = {
  courtSms: 'POST /automation/court-sms',
  docConvert: 'POST /doc-convert/convert',
  docConverter: 'POST /doc-converter/jobs',
  lpr: 'POST /lpr/calculate',
} as const

/** 周一起始的星期标题 */
export const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日'] as const
