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

/**
 * 第二引擎（交叉比对用）：`paddleocr_vl` 不是可注册的解析平台
 * （`DocumentParseProvider.ProviderType` 只有 mineru / textin），它走的是
 * `PaddleOCRApiEngine` 独立路径，所以**不能**塞进 `cloud_backend`——
 * 后端 `resolve_cloud_backends` 会把不认识的单值按 auto 静默降级。
 */
export type DualEngine = 'mineru' | 'paddleocr_vl' | 'textin'

export async function createPdfSplitJob(
  file: File,
  opts: {
    layoutMode?: 'fast_text' | 'layout'
    cloudBackend?: CloudBackend
    /** ≥2 个引擎时才传：逗号分隔的全部所选引擎（含正主），后端据此另起比对 */
    dualEngines?: string | null
  } = {},
): Promise<string> {
  const body = new FormData()
  body.append('file', file, file.name)
  body.append('template_key', 'filing_materials_v1')
  body.append('split_mode', 'content_analysis')
  body.append('ocr_profile', 'accurate')
  // 版面策略：layout 让电子版 PDF 也上云端拿版面块与坐标（原文坐标对照需要），
  // 代价是这些页也计费且更慢；默认 fast_text 不调云端。
  body.append('layout_mode', opts.layoutMode ?? 'fast_text')
  // 平台偏好：auto 会自动容灾（首选失败切下一个）；锁定则只用该平台、失败即失败。
  // **只收单值**：多选时由调用方（platform-selection 的 resolveBackendRequest）
  // 先算出正主，其余引擎走下面的独立字段。
  body.append('cloud_backend', opts.cloudBackend ?? 'auto')
  // 交叉比对：≥2 个引擎时才有。独立字段而不是拼进 cloud_backend——
  // 后者只认单值，拼成逗号串会被后端当成未知值按 auto 处理，用户勾的引擎就白勾了。
  if (opts.dualEngines) body.append('dual_engines', opts.dualEngines)
  const result = await pdfSplitApi
    .post('jobs', { body, timeout: UPLOAD_TIMEOUT_MS })
    .json<PdfSplitJobSubmit>()
  return result.job_id
}

/**
 * 从一份 PDF 里按页范围切出小 PDF（POST /pdf-splitting/extract-pages）。
 *
 * `pageStart` / `pageEnd` 均为 1 起、含两端。服务端复用导出链本来的切页实现，
 * 不在前端揣页逻辑（浏览器端也没装 pdf-lib）。
 *
 * 主要用于归案：每份案件材料上传的是它自己那几页，而不是整卷 164 页。
 * 失败直接抛，由调用方决定是否降级为整包上传。
 */
export async function extractPdfPages(
  file: Blob,
  name: string,
  pageStart: number,
  pageEnd: number,
): Promise<Blob> {
  const body = new FormData()
  body.append('file', new File([file], name, { type: 'application/pdf' }))
  body.append('page_start', String(pageStart))
  body.append('page_end', String(pageEnd))
  const res = await pdfSplitApi.post('extract-pages', { body, timeout: UPLOAD_TIMEOUT_MS })
  return await res.blob()
}

export async function getPdfSplitJob(jobId: string): Promise<PdfSplitJobPayload> {
  return pdfSplitApi.get(`jobs/${jobId}`).json<PdfSplitJobPayload>()
}

/**
 * 查一份**正在进行中**的拆分任务（GET /pdf-splitting/inflight-job）。
 *
 * 为什么需要：任务一旦发起就只活在发起页面的内存里。刷新、换设备、或者同事先
 * 点了一次「自动分段」，当前阅读器毫不知情——界面上没有进度，再点一次又会
 * 并行跑第二份 164 页（钱翻倍）。这就是所谓的「幽灵任务」。
 *
 * 命中就由阅读器接管轮询并在底部进度条上显示，不需要用户再点按钮。
 * 返回 null 表示没有进行中的任务。失败同样静默返回 null：查在飞任务只是**优化**，
 * 查不到最多是少一个进度条，不该让整个识别入口跟着报错。
 */
export async function findInflightPdfSplitJob(
  sourceName: string,
  totalPages?: number,
): Promise<PdfSplitJobPayload | null> {
  const searchParams: Record<string, string | number> = { source_name: sourceName }
  if (totalPages != null && totalPages > 0) searchParams.total_pages = totalPages
  try {
    return await pdfSplitApi.get('inflight-job', { searchParams }).json<PdfSplitJobPayload | null>()
  } catch {
    return null
  }
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
