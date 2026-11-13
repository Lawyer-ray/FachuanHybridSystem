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

/**
 * 查一份**已算好**的拆分任务（按原始文件名 + 页数三重匹配）。
 *
 * 为什么需要：律师跑完一次 164 页识别（云端 OCR + LLM 分段，5-10 分钟、几十元）
 * 后，只要 `draft_state` 没被回写（没点过「自动识别」，或换了浏览器），
 * 阅读器就拿不到结果；此时再点一次会从零重跑，前面的钱和时间全白花。
 *
 * 返回 null 表示没有可复用的，调用方照常新建任务。
 */
export async function findReusablePdfSplitJob(
  sourceName: string,
  totalPages?: number,
): Promise<PdfSplitJobPayload | null> {
  const searchParams: Record<string, string | number> = { source_name: sourceName }
  if (totalPages != null && totalPages > 0) searchParams.total_pages = totalPages
  try {
    return await pdfSplitApi.get('reusable-job', { searchParams }).json<PdfSplitJobPayload | null>()
  } catch {
    // 查复用是**优化**，失败不该阻断识别主流程——降级为「没有可复用的」
    return null
  }
}
