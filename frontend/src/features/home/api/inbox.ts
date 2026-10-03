import { parseISO } from 'date-fns'

import { createApiClient } from '@/lib/api'
import type { InboxMessage } from '@/features/material-prep'
import type { InboxItem } from '../types'

/** 待处理流入 / 收件箱资源（/api/v1/inbox）+ 归一化。 */

export const inboxApi = createApiClient({ prefix: '/api/v1/inbox' })

/** 首页收件箱卡的 query key（InboxCard 订阅，court-sms 提交后 invalidate） */
export const HOME_INBOX_KEY = ['home-inbox'] as const

/** 后端 InboxMessageOut（/inbox/messages）——material-prep 域 InboxMessage 的投影，
 *  只声明首页卡用到的字段（类型来源唯一，避免两份手抄漂移） */
export type InboxMessageOut = Pick<
  InboxMessage,
  | 'id'
  | 'source_name'
  | 'source_type'
  | 'subject'
  | 'sender'
  | 'recipient'
  | 'received_at'
  | 'has_attachments'
  | 'attachment_count'
  | 'segs'
  | 'named'
  | 'pages'
  | 'mats'
  | 'types'
  | 'compose'
  | 'created_at'
>

const INBOX_ICON: Record<string, InboxItem['kind']> = {
  court_sms: 'sms',
  court_inbox: 'mail',
  manual_upload: 'mat',
  email: 'mail',
}

/**
 * 收件箱条目的 status 说明（保留给未来处理流参考）：
 * InboxMessage 模型没有 status 字段——它来自 draft_state 这个 JSONField 里的
 * status 键，只有材料预处理页（manual_upload）会写 done/filed，其余来源恒为 todo。
 * 首页收件箱卡刻意只做「最近流入」展示，不消费 status / 动作按钮（实测 338 条里
 * 336 条恒为 todo，计数与按钮都没有信息量），故 toInboxItem 不再组装这些字段。
 */

/** 收件箱条目 → 最近流入展示态（类型 + 来源 + 时间） */
function toInboxItem(m: InboxMessageOut): InboxItem {
  const kind = INBOX_ICON[m.source_type] ?? 'mat'
  return {
    id: m.id,
    kind,
    sourceLabel: m.source_name,
    who: m.sender,
    title: m.subject,
    at: formatRelative(m.received_at),
    hot: kind === 'sms',
  }
}

/** 取待处理流入：收件箱按收到时间倒序（后端已排序），limit 走服务端截取（默认 6 条） */
export async function listInbox(limit = 6): Promise<InboxItem[]> {
  const rows = await inboxApi.get('messages', { searchParams: { limit } }).json<InboxMessageOut[]>()
  return rows.slice(0, limit).map(toInboxItem)
}

/** received_at → 相对时间（今天 HH:mm / 昨天 HH:mm / M月D日）。
 *  parseISO 而非 new Date：后者对 date-only / 空格分隔等非严格 ISO 形态
 *  按 UTC 解析（见 CalendarPanel 的 parseKey 教训），naive 串会偏移。 */
export function formatRelative(iso: string): string {
  const d = parseISO(iso)
  if (Number.isNaN(d.getTime())) return ''
  const now = new Date()
  const sameDay = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
  const hhmm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  if (sameDay(d, now)) return `今天 ${hhmm}`
  if (sameDay(d, yesterday)) return `昨天 ${hhmm}`
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日`
}
