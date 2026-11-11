import { createApiClient, UPLOAD_TIMEOUT_MS } from '@/lib/api'
import type { components } from '@/types/api-schema'

// isEmptyDraft 直连 ../draft/state 而非 barrel：经 barrel 会因 resolve → ../api 的
// 既有依赖形成 api ↔ draft 环（见 draft/index.ts 头注释）
import { isEmptyDraft } from '../draft/state'
import { PACK_SOURCE_TYPES } from '../constants'
import type { AssignInfo, DraftState, InboxMessage, InboxMessageDetail, PackStatus } from '../types'

/**
 * 材料预处理对接的是后端收件箱（/api/v1/inbox）。
 * 每次上传（可多文件）会生成一条 manual_upload 来源的消息，即一个「材料包」。
 */
export const inboxApi = createApiClient({ prefix: '/api/v1/inbox' })

export async function listMaterialPacks(): Promise<InboxMessage[]> {
  return inboxApi
    .get('messages', {
      // limit 显式对齐服务端兜底默认（500）：收件箱持续增长，桌面仓库列表
      // 在超过该量级前需要真正的分页/筛选，而不是无限拉全量
      searchParams: { source_type: PACK_SOURCE_TYPES, has_attachments: 'true', limit: '500' },
    })
    .json<InboxMessage[]>()
}

export async function getPackDetail(id: number): Promise<InboxMessageDetail> {
  return inboxApi.get(`messages/${id}`).json<InboxMessageDetail>()
}

/** 删除材料包（收件箱消息）：后端先清理附件物理文件，再删 DB 记录。
 *  响应为生成物 MessageAckOut（{ok, message_id}） */
export async function deletePack(id: number): Promise<components['schemas']['MessageAckOut']> {
  return inboxApi.delete(`messages/${id}`).json()
}

/** 重命名材料包标题（收件箱消息 subject）。
 *  响应为生成物 MessageRenameOut（{ok, message_id, subject}） */
export async function renamePack(
  id: number,
  subject: string,
): Promise<components['schemas']['MessageRenameOut']> {
  return inboxApi.put(`messages/${id}`, { json: { subject } }).json()
}

function toFormData(files: File[], subject?: string): FormData {
  const fd = new FormData()
  if (subject) fd.append('subject', subject)
  for (const f of files) fd.append('files', f, f.name)
  return fd
}

export async function uploadPack(files: File[], subject?: string): Promise<InboxMessageDetail> {
  return inboxApi
    .post('messages/upload', {
      body: toFormData(files, subject),
      timeout: UPLOAD_TIMEOUT_MS,
    })
    .json<InboxMessageDetail>()
}

/** 阅读器内追加材料：往现有材料包再收一批文件，返回更新后的详情 */
export async function appendPackFiles(id: number, files: File[]): Promise<InboxMessageDetail> {
  return inboxApi
    .post(`messages/${id}/attachments`, {
      body: toFormData(files),
      timeout: UPLOAD_TIMEOUT_MS,
    })
    .json<InboxMessageDetail>()
}

/** 只打标（未拆分）时的最小回写载荷：后端把 draft_state 当不透明 JSON 存储，
 *  从未拆分过的包写 {status[, assign]} 即可，阅读器打开时会按材料重建完整草稿。
 *  用精确联合而非 Partial<DraftState> / unknown——只为这一条合法的窄载荷开口，
 *  其余调用方仍必须交完整 DraftState。 */
export type PackStatusPatch = Pick<DraftState, 'status' | 'assign'>

/** 保存拆分草稿（整份 DraftState，或 setPackStatusRemote 的最小打标载荷） */
export async function saveDraft(id: number, draft: DraftState | PackStatusPatch): Promise<void> {
  await inboxApi.put(`messages/${id}/draft`, { json: { draft } }).json()
}

/** 只打标材料包状态（不接归档 / 归案），保留已有 draft_state 的拆分内容 */
export async function setPackStatusRemote(
  id: number,
  status: PackStatus,
  assign?: AssignInfo,
): Promise<void> {
  const detail = await getPackDetail(id)
  // draft_state 在未拆分过的包上是空占位 {}（判别见 draft/state.ts），守卫式
  // 窄化而非 as 抹掉联合：空占位无内容可保留，只写 status / assign（与历史
  // 行为一致）；有效草稿整份带上，不丢 mats/segs/infos。
  const draft: DraftState | PackStatusPatch = isEmptyDraft(detail.draft_state)
    ? { status }
    : { ...detail.draft_state, status }
  await saveDraft(id, assign ? { ...draft, assign } : draft)
}
