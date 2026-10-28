import { createApiClient } from '@/lib/api'
import { friendlyTime } from '@/lib/format'
import type { InboxMessage } from '@/features/material-prep'
import type { InboxItem } from '../types'
/** 待处理流入 / 收件箱资源（/api/v1/inbox）+ 归一化。 */

export const inboxApi = createApiClient({ prefix: '/api/v1/inbox' })

/** 首页收件箱卡的 query key（InboxCard 订阅，court-sms 提交后 invalidate） */
export const HOME_INBOX_KEY = ['home-inbox'] as const

/** 后端 InboxMessageOut（/inbox/messages）——material-prep 域 InboxMessage 的投影，
 *  只声明首页卡用到的字段（类型来源唯一，避免两份手抄漂移）。
 *
 *  除展示字段外，还必须有：`converted_message_id`（已转过的直接开包）、
 *  `has_attachments` + `source_type`（?能不能转包，与收件箱页 canConvert 同口径）。
 *  `status` 不收：那是 material-prep 写在 draft_state 里的自有语义，对收件箱
 *  卡（只展示最近流入）没有信息量。 */
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
  | 'is_read'
  | 'converted_message_id'
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

/** 本身就是材料包（律师手动包 / 客户链接包）——点行直接进阅读器，不必先转 */
function isPackSource(sourceType: string): boolean {
  return sourceType === 'manual_upload' || sourceType === 'client_upload'
}

/**
 * 「点这行该进材料预处理，还是就地展开读详情」。
 *
 * 材料包天然该进阅读器；已转过的消息（converted_message_id 非空）直接打开
 * 已转的包，不重复搬运；其余一律就地展开——一张网告知书、判决书送达通知、
 * 邮件这类绝大多数是**纯通知**，硬塞进材料预处理只会得到一个空包 +
 * 「附件解析失败」的误导提示。
 */
function packIdOf(m: InboxMessageOut): number | null {
  if (isPackSource(m.source_type)) return m.id
  return m.converted_message_id ?? null
}

/** 收件箱条目 → 最近流入展示态（类型 + 来源 + 时间）。
 *  相对时间（今天/昨天 HH:mm、其余 M 月 D 日）由 @/lib/format 的 friendlyTime
 *  提供（与 material-prep 材料卡共用，格式差异走 opts）。 */
function toInboxItem(m: InboxMessageOut): InboxItem {
  const kind = INBOX_ICON[m.source_type] ?? 'mat'
  const packId = packIdOf(m)
  return {
    id: m.id,
    kind,
    sourceLabel: m.source_name,
    who: m.sender,
    title: m.subject,
    at: friendlyTime(m.received_at),
    hot: kind === 'sms',
    packId,
    // 转材料包只在「有附件 + 非材料包来源 + 还没转过」时有意义，与收件箱页
    // types.ts 的 canConvert 同口径
    canConvert: m.has_attachments && packId == null && !isPackSource(m.source_type),
    // 原始行透传（只带就地展开需要的字段，见 types.ts 的 InboxMessageOut）
    row: m,
  }
}

/** 取待处理流入：收件箱按收到时间倒序（后端已排序），limit 走服务端截取（默认 6 条） */
export async function listInbox(limit = 6): Promise<InboxItem[]> {
  const rows = await inboxApi.get('messages', { searchParams: { limit } }).json<InboxMessageOut[]>()
  return rows.slice(0, limit).map(toInboxItem)
}
