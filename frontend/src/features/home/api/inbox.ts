import { createApiClient } from '@/lib/api'
import type { InboxItem } from '../types'

/** 待处理流入 / 收件箱资源（/api/v1/inbox）+ 归一化。 */

export const inboxApi = createApiClient({ prefix: '/api/v1/inbox' })

/** 后端 InboxMessageOut（/inbox/messages）——只声明前端用到的字段 */
export interface InboxMessageOut {
  id: number
  source_name: string
  source_type: string
  subject: string
  sender: string
  recipient: string
  received_at: string
  has_attachments: boolean
  attachment_count: number
  status: string
  segs: number
  named: number
  pages: number
  mats: number
  types: string[]
  compose: string
  created_at: string
}

const INBOX_ICON: Record<string, InboxItem['kind']> = {
  court_sms: 'sms',
  court_inbox: 'mail',
  manual_upload: 'mat',
  email: 'mail',
}

/**
 * 收件箱条目的处理状态。
 *
 * 注意：InboxMessage 模型**没有** status 字段——它来自 draft_state 这个
 * JSONField 里的 status 键（backend/apps/message_hub/schemas.py 的
 * resolve_status）。后端把 draft_state 当不透明数据，语义由前端定义；
 * 写入方是材料预处理页（右键「已归案 / 归档留痕」）。
 *
 * 所以：
 *   - 只有 manual_upload（材料包）会被真正标成 done/filed
 *   - 法院短信 / 邮件这些非材料包来源没有拆分流程，status 恒为 todo
 *   - 展示时按来源分别给文案，别把「归案」安到法院短信头上
 */
const PACK_STATUS_LABEL: Record<string, string> = {
  todo: '待处理',
  done: '已归案',
  filed: '不接归档',
}

/** 收件箱条目 → 待处理流入展示态（含类型、状态、操作按钮） */
function toInboxItem(m: InboxMessageOut): InboxItem {
  const kind = INBOX_ICON[m.source_type] ?? 'mat'
  const hot = kind === 'sms'
  return {
    id: m.id,
    kind,
    sourceLabel: m.source_name,
    who: m.sender,
    title: m.subject,
    at: formatRelative(m.received_at),
    status: PACK_STATUS_LABEL[m.status] ?? m.status,
    // 动作按来源给：材料包才能解析，法院短信是归案，邮件/其他是打开
    action: kind === 'mat' ? '解析' : hot ? '归案' : '打开',
    hot,
  }
}

/** 取待处理流入：收件箱按收到时间倒序（后端已排序），取前 limit 条 */
export async function listInbox(limit = 6): Promise<InboxItem[]> {
  const rows = await inboxApi.get('messages').json<InboxMessageOut[]>()
  return rows.slice(0, limit).map(toInboxItem)
}

/** received_at → 相对时间（今天 HH:mm / 昨天 HH:mm / M月D日） */
export function formatRelative(iso: string): string {
  const d = new Date(iso)
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
