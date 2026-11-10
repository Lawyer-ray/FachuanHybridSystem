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

// ── 来源同步 ──────────────────────────────────────────────
//
// 接口在同一个 /api/v1/inbox 域下（sources / sources/sync-all / sources/{id}/sync），
// 挂载前缀已按后端 openapi.json 核对，不猜。

type MessageSourceOut = components['schemas']['MessageSourceOut']

/** 同步目标的状态判据：后端 SyncStatus 只有 pending/success/failed，没有 running，
 *  所以「跑完了没有」不能看 last_sync_status，只能看 last_sync_at 是否更新。 */
export interface SourceSyncSnapshot {
  id: number
  last_sync_at: string | null
  last_sync_status: string
}

/** GET /inbox/sources —— 消息来源列表（后端已按可见性收敛） */
export async function listSources(): Promise<MessageSourceOut[]> {
  return inboxApi.get('sources').json<MessageSourceOut[]>()
}

/**
 * 前端手动同步的默认窗口（天）。
 *
 * 手动同步的预期是「点一下立刻看到最近的新消息」，不是「把邮箱历史翻一遍」。
 * 实测某邮箱半年 290 封里只有 2 封是真正关心的到账通知，全量拉取既慢又污染收件箱。
 *
 * **只影响手动同步**：后台定时任务与首次建源不走这个值（后端传 None 时按来源的
 * sync_since 全量回填），所以「从历史时期完整同步」仍会发生在初次回填。
 */
export const DEFAULT_SYNC_WINDOW_DAYS = 7

/** 手动同步可选的时间范围（天数）。7 = 默认。 */
export const SYNC_WINDOW_OPTIONS = [7, 30, 90] as const
export type SyncWindowDays = (typeof SYNC_WINDOW_OPTIONS)[number]

/** POST /inbox/sources/sync-all —— 提交全部可见来源的同步任务 */
export async function syncAllSources(days: SyncWindowDays = DEFAULT_SYNC_WINDOW_DAYS): Promise<{ success: boolean; message: string }> {
  return inboxApi
    .post('sources/sync-all', { searchParams: { days: String(days) } })
    .json<{ success: boolean; message: string }>()
}

/** POST /inbox/sources/{id}/sync —— 提交单个来源的同步任务 */
export async function syncSource(
  id: number,
  days: SyncWindowDays = DEFAULT_SYNC_WINDOW_DAYS,
): Promise<{ success: boolean; message: string }> {
  return inboxApi.post(`sources/${id}/sync`, { searchParams: { days: String(days) } }).json<{ success: boolean; message: string }>()
}

// ── 邮件 → 在办合同 自动关联候选 ──────────────────────────
//
// 一期只读：只给候选与理由，不写任何财务数据。律师看过后自己去合同里关联。

export interface ContractMatchCandidate {
  contract_id: number
  contract_name: string
  score: number
  reasons: string[]
  outstanding_amount: string | null
  fee_mode: string
  caveat: string
}

export interface ContractMatchResult {
  /** confident=有确定匹配（仍需求律师确认）/ suggested=弱候选 / none=无候选 */
  status: 'confident' | 'suggested' | 'none'
  candidates: ContractMatchCandidate[]
  extracted_amounts: string[]
  extracted_case_numbers: string[]
}

/** GET /inbox/messages/{id}/contract-match —— 这条邮件可能关联的在办合同 */
export async function getContractMatch(messageId: number): Promise<ContractMatchResult> {
  return inboxApi.get(`messages/${messageId}/contract-match`).json<ContractMatchResult>()
}
