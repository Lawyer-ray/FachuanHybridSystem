import { createApiClient } from '@/lib/api'
import type { InboxMessage, InboxMessageDetail, DraftState } from './types'

/**
 * 材料预处理对接的是后端收件箱（/api/v1/inbox）。
 * 每次上传（可多文件）会生成一条 manual_upload 来源的消息，即一个「材料包」。
 */
export const inboxApi = createApiClient({ prefix: `/inbox` })

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

export async function uploadPack(files: File[], subject?: string): Promise<InboxMessageDetail> {
  return inboxApi
    .post('messages/upload', {
      body: toFormData(files, subject),
    })
    .json<InboxMessageDetail>()
}

/** 保存拆分草稿 */
export async function saveDraft(id: number, draft: DraftState): Promise<void> {
  await inboxApi.put(`messages/${id}/draft`, { json: { draft } }).json()
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
