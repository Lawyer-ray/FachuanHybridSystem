import { LONG_TASK_TIMEOUT_MS } from './timeouts'
import { casesApi } from './cases'

// ───────────────────────── 材料归案 ─────────────────────────
// 材料（CaseMaterial）挂在 `/api/v1/cases` 前缀下，所以复用 `casesApi`，
// 不另建客户端 —— 多建一个同前缀 client 只会让「7 个 prefix」这条约定失真。

/** 材料条款（对齐后端 CaseMaterialBindItemIn） */
export interface MaterialBindItem {
  attachment_id: number
  category: string
  type_name: string
  side?: string | null
  type_id?: number | null
  party_ids?: number[]
  supervising_authority_id?: number | null
}

/**
 * 把已上传的附件**归案**成材料。
 *
 * ⚠️ upload 只是把字节塞进案件日志；bind 才让它成为 CaseMaterial。
 * 材料齐备度 / 起诉条件 / 一张网立案读的都是 CaseMaterial ——
 * 只 upload 不 bind，界面会显示「材料齐备 0/6」但文件明明传上去了。
 */
export async function bindMaterials(
  caseId: number,
  items: MaterialBindItem[],
): Promise<{ saved_count: number }> {
  return casesApi.post(`${caseId}/materials/bind`, { json: { items } }).json<{ saved_count: number }>()
}

/** 上传文件到案件（返回附件 id，供 bind 使用） */
export async function uploadCaseMaterials(
  caseId: number,
  files: File[],
): Promise<{ log_id: number; attachment_ids: number[] }> {
  const form = new FormData()
  // ⚠️ 字段名是 `files`（复数）—— 写 `file` 会静默成功但不真的上传，
  //    返回 attachment_ids: []，然后 bind 时找不到附件。
  for (const f of files) form.append('files', f)
  return casesApi
    .post(`${caseId}/materials/upload`, { body: form, timeout: LONG_TASK_TIMEOUT_MS })
    .json<{ log_id: number; attachment_ids: number[] }>()
}

/** 归案候选（已上传但还没变成材料的附件） */
export interface BindCandidate {
  attachment_id: number
  file_name: string
  uploaded_at: string
}

export async function listBindCandidates(caseId: number): Promise<BindCandidate[]> {
  return casesApi.get(`${caseId}/materials/bind-candidates`).json<BindCandidate[]>()
}
