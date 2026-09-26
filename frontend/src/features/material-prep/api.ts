import { createApiClient } from '@/lib/api'
import type {
  AssignInfo,
  CaseRow,
  ClientHit,
  DraftState,
  InboxMessage,
  InboxMessageDetail,
  OcrResult,
  PackStatus,
  PdfSplitSegmentSuggestion,
} from './types'

/**
 * 材料预处理对接的是后端收件箱（/api/v1/inbox）。
 * 每次上传（可多文件）会生成一条 manual_upload 来源的消息，即一个「材料包」。
 */
export const inboxApi = createApiClient({ prefix: '/api/v1/inbox' })

/** 客户/当事人检索（/api/v1/client/parties/search，精简字段，兼容证件档案为空的客户） */
export const clientApi = createApiClient({ prefix: '/api/v1/client' })
const pdfSplitApi = createApiClient({ prefix: '/api/v1/pdf-splitting' })

interface PdfSplitJobPayload {
  job_id: string
  status: string
  progress: number
  segments: PdfSplitSegmentSuggestion[]
  error_message: string
}

export async function createPdfSplitJob(file: File): Promise<string> {
  const body = new FormData()
  body.append('file', file, file.name)
  body.append('template_key', 'filing_materials_v1')
  body.append('split_mode', 'content_analysis')
  body.append('ocr_profile', 'accurate')
  const result = await pdfSplitApi.post('jobs', { body }).json<{ job_id: string }>()
  return result.job_id
}

export async function getPdfSplitJob(jobId: string): Promise<PdfSplitJobPayload> {
  return pdfSplitApi.get(`jobs/${jobId}`).json<PdfSplitJobPayload>()
}

/**
 * 按关键字模糊检索当事人。
 * isOurClient 限定范围：委托人传 true（我方当事人）、对方当事人传 false。
 */
export async function searchClients(keyword: string, isOurClient: boolean): Promise<ClientHit[]> {
  return clientApi
    .get('parties/search', {
      searchParams: { keyword, is_our_client: isOurClient ? 'true' : 'false' },
    })
    .json<ClientHit[]>()
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

/**
 * 取附件字节（带鉴权），按 messageId:partIndex 缓存。供 PDF.js 渲染、OCR 取字、云端识别上传。
 *
 * 返回的是缓存的 buffer 本体（调用方会反复复用：每页渲染、OCR、识别上传各取一次）。
 * 若某个调用方会把 buffer **transfer** 给 worker 导致它被 detach（PDF.js 的
 * getDocument({ data }) 就是），请在该调用方内部先拷贝再传——不要在这里拷，
 * 否则 92 页的材料会凭空多拷 92 次。详见 lib/pdf.ts 的 loadPdfDocument。
 */
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
