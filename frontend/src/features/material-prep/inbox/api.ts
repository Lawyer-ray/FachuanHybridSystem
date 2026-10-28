import { createApiClient } from '@/lib/api'
import type { components } from '@/types/api-schema'
import type { InboxRow, InboxSourceFilter, ReadStateResult, ConvertResult } from './types'

/**
 * 收件箱页对接的资源（/api/v1/inbox）。
 *
 * 与 material-prep 共用同一个后端域，但用途不同：material-prep 只读
 * manual_upload/client_upload 材料包；本页读**全部来源**（一张网、邮箱、
 * 短信、材料包），是「消息流入的总入口」。两个 feature 各自持有客户端，
 * 互不 import（前端规范：禁止 feature 互相引用内部文件）。
 *
 * 字段形状一律取生成物 InboxMessageOut，不手抄（见 types.ts 的投影说明）。
 */
export const inboxApi = createApiClient({ prefix: '/api/v1/inbox' })

/** 收件箱列表 query key（收件箱页订阅；材料包上传/转换后由各自 mutation invalidate） */
export const INBOX_LIST_KEY = ['inbox-list'] as const

/** 列表默认取多少条：收件箱是持续增长的慢数据，首屏不必拉全量 */
export const INBOX_PAGE_SIZE = 200

type InboxMessageOut = components['schemas']['InboxMessageOut']

/** 后端 source_type 多值过滤（逗号分隔，与 material_prep 的 PACK_SOURCE_TYPES 同协议） */
function sourceTypeParam(filter: InboxSourceFilter): string | undefined {
  return filter === 'all' ? undefined : filter
}

export interface ListInboxParams {
  source?: InboxSourceFilter
  unreadOnly?: boolean
  search?: string
  limit?: number
}

/** GET /inbox/messages —— 收件箱列表（后端已按 received_at 倒序） */
export async function listInbox(params: ListInboxParams = {}): Promise<InboxRow[]> {
  const searchParams: Record<string, string> = { limit: String(params.limit ?? INBOX_PAGE_SIZE) }
  const sourceType = sourceTypeParam(params.source ?? 'all')
  if (sourceType) searchParams.source_type = sourceType
  if (params.unreadOnly) searchParams.unread_only = 'true'
  const search = params.search?.trim()
  if (search) searchParams.search = search
  return inboxApi.get('messages', { searchParams }).json<InboxRow[]>()
}

/** GET /inbox/messages/{id} —— 消息详情（含正文与附件清单） */
export async function getInboxMessage(id: number): Promise<components['schemas']['InboxMessageDetailOut']> {
  return inboxApi.get(`messages/${id}`).json<components['schemas']['InboxMessageDetailOut']>()
}

/** POST /inbox/messages/{id}/read —— 标记已读 / 未读（幂等） */
export async function setReadState(id: number, read: boolean): Promise<ReadStateResult> {
  return inboxApi.post(`messages/${id}/read`, { json: { read } }).json<ReadStateResult>()
}

/** POST /inbox/messages/{id}/convert —— 外部来源消息转材料包（幂等，返回 pack_id） */
export async function convertToPack(id: number): Promise<ConvertResult> {
  return inboxApi.post(`messages/${id}/convert`).json<ConvertResult>()
}

/** 附件下载 / 预览 URL。
 *
 *  ⚠️ **不能直接当 `<a href>` 用**：本应用的 JWT 在 localStorage，只有 ky 发
 *  请求时才带 `Authorization`；浏览器导航带不上它，后端 JWTOrSessionAuth 也
 *  不收 `?token=`（安全审计 2026Q4 M-2）。直接打开此 URL 会得到 401。
 *
 *  正确用法：经 `withDownloadTicket()` 换一次性票据后拼 `?ticket=` 再打开
 *  （见 MessageDrawer 的 openAttachment，以及办案文档的 preview/download）。
 */
export function attachmentUrl(messageId: number, partIndex: number, inline: boolean): string {
  const kind = inline ? 'preview' : 'download'
  return `/api/v1/inbox/messages/${messageId}/attachments/${partIndex}/${kind}`
}

export type { InboxMessageOut }
