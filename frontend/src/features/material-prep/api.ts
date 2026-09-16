import { createApiClient } from '@/lib/api'
import type {
  AssignInfo,
  CaseRow,
  ClientHit,
  InboxMessage,
  InboxMessageDetail,
  DraftState,
  OcrResult,
  PackStatus,
} from './types'

/**
 * 材料预处理对接的是后端收件箱（/api/v1/inbox）。
 * 每次上传（可多文件）会生成一条 manual_upload 来源的消息，即一个「材料包」。
 */
export const inboxApi = createApiClient({ prefix: '/api/v1/inbox' })

/** 客户/当事人检索（/api/v1/client/clients） */
export const clientApi = createApiClient({ prefix: '/api/v1/client' })

/** 按关键字模糊检索当事人（客户库，后端按 name/phone/id_number 做 icontains），用于委托人/对方当事人填入 */
export async function searchClients(keyword: string): Promise<ClientHit[]> {
  return clientApi.get('clients', { searchParams: { search: keyword } }).json<ClientHit[]>()
}

export async function listMaterialPacks(): Promise<InboxMessage[]> {
  return inboxApi
    .get('messages', {
      searchParams: { source_type: 'manual_upload', has_attachments: 'true' },
    })
    .json<InboxMessage[]>()
}

export async function getPackDetail(id: number): Promise<InboxMessageDetail> {
  return inboxApi.get(`messages/${id}`).json<InboxMessageDetail>()
}

/** 删除材料包（收件箱消息）：后端先清理附件物理文件，再删 DB 记录 */
export async function deletePack(id: number): Promise<{ ok: boolean; message_id: number }> {
  return inboxApi.delete(`messages/${id}`).json()
}

/** 重命名材料包标题（收件箱消息 subject） */
export async function renamePack(id: number, subject: string): Promise<{ ok: boolean; message_id: number; subject: string }> {
  return inboxApi.put(`messages/${id}`, { json: { subject } }).json()
}

export async function uploadPack(files: File[], subject?: string): Promise<InboxMessageDetail> {
  return inboxApi
    .post('messages/upload', {
      body: toFormData(files, subject),
    })
    .json<InboxMessageDetail>()
}

/** 阅读器内追加材料：往现有材料包再收一批文件，返回更新后的详情 */
export async function appendPackFiles(id: number, files: File[]): Promise<InboxMessageDetail> {
  return inboxApi
    .post(`messages/${id}/attachments`, {
      body: toFormData(files),
    })
    .json<InboxMessageDetail>()
}

/** 保存拆分草稿 */
export async function saveDraft(id: number, draft: DraftState): Promise<void> {
  await inboxApi.put(`messages/${id}/draft`, { json: { draft } }).json()
}

/** 只打标材料包状态（不接归档 / 归案），保留已有 draft_state 的拆分内容 */
export async function setPackStatusRemote(
  id: number,
  status: PackStatus,
  assign?: AssignInfo,
): Promise<void> {
  const detail = await getPackDetail(id)
  const draft = detail.draft_state ?? {}
  await saveDraft(id, {
    ...draft,
    status,
    ...(assign ? { assign } : {}),
  })
}

/** 框选取字：把页面图片交给 RapidOCR，返回归一化文字块 */
export async function ocrImage(image: Blob): Promise<OcrResult> {
  const fd = new FormData()
  fd.append('file', image, 'page.png')
  return inboxApi.post('ocr', { body: fd }).json<OcrResult>()
}

/** 搜索真实案件（归案 modal 用） */
export async function searchCases(q: string): Promise<CaseRow[]> {
  if (!q.trim()) return []
  const base = createApiClient() // prefix = API_BASE_URL(/api/v1)
  return base.get('cases/search', { searchParams: { q, limit: '10' } }).json<CaseRow[]>()
}

const bytesCache = new Map<string, Promise<ArrayBuffer>>()

/** 取附件字节（带鉴权），按 messageId:partIndex 缓存。供 PDF.js 渲染。 */
export function fetchAttachmentBytes(messageId: number, partIndex: number): Promise<ArrayBuffer> {
  const key = `${messageId}:${partIndex}`
  const hit = bytesCache.get(key)
  if (hit) return hit
  const p = inboxApi
    .get(`messages/${messageId}/attachments/${partIndex}/preview`)
    .then((res) => res.arrayBuffer())
    .catch((e) => {
      bytesCache.delete(key)
      throw e
    })
  bytesCache.set(key, p)
  return p
}

export function clearBytesCache(): void {
  bytesCache.clear()
}

function toFormData(files: File[], subject?: string): FormData {
  const fd = new FormData()
  if (subject) fd.append('subject', subject)
  for (const f of files) fd.append('files', f, f.name)
  return fd
}
