import { createApiClient, UPLOAD_TIMEOUT_MS } from '@/lib/api'
import type { components } from '@/types/api-schema'

const pdfSplitApi = createApiClient({ prefix: '/api/v1/pdf-splitting' })

/** GET /pdf-splitting/jobs/{job_id} 的响应（生成物 PdfSplitJobOut）。
 *  后端已修复 OpenAPI 组件名冲突（此前该端点误挂 doc-converter 的 JobOut，
 *  缺 job_id / segments 字段），schema 与实际响应一致，直接取生成物。 */
type PdfSplitJobPayload = components['schemas']['PdfSplitJobOut']

/** POST /pdf-splitting/jobs 的响应（生成物 PdfSplitJobSubmitOut） */
type PdfSplitJobSubmit = components['schemas']['PdfSplitJobSubmitOut']

/** 云端解析平台偏好：auto=优先+容灾；锁定值=只用它，失败不降级 */
export type CloudBackend = 'auto' | 'mineru' | 'textin'

export async function createPdfSplitJob(
  file: File,
  opts: { layoutMode?: 'fast_text' | 'layout'; cloudBackend?: CloudBackend } = {},
): Promise<string> {
  const body = new FormData()
  body.append('file', file, file.name)
  body.append('template_key', 'filing_materials_v1')
  body.append('split_mode', 'content_analysis')
  body.append('ocr_profile', 'accurate')
  // 版面策略：layout 让电子版 PDF 也上云端拿版面块与坐标（原文坐标对照需要），
  // 代价是这些页也计费且更慢；默认 fast_text 不调云端。
  body.append('layout_mode', opts.layoutMode ?? 'fast_text')
  // 平台偏好：auto 会自动容灾（首选失败切下一个）；锁定则只用该平台、失败即失败
  body.append('cloud_backend', opts.cloudBackend ?? 'auto')
  const result = await pdfSplitApi
    .post('jobs', { body, timeout: UPLOAD_TIMEOUT_MS })
    .json<PdfSplitJobSubmit>()
  return result.job_id
}

export async function getPdfSplitJob(jobId: string): Promise<PdfSplitJobPayload> {
  return pdfSplitApi.get(`jobs/${jobId}`).json<PdfSplitJobPayload>()
}
