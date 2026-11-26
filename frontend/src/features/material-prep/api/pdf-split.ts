import { createApiClient, UPLOAD_TIMEOUT_MS } from '@/lib/api'
import type { components } from '@/types/api-schema'

/**
 * 拆分域路由前缀。**单点定义**：ky 客户端与下面三个下载直链共用同一个字符串。
 * 口径来源：后端 `apiSystem/api.py` 的 `api_v1.add_router("/pdf-splitting", ...)`，
 * 与 `GET /pdf-splitting/jobs/{job_id}` 同一前缀——不猜、不另抄一份。
 * 直链若自己拼（写死 `/api/v1`，或漏掉 `/pdf-splitting`），只会在用户点下载时
 * 才暴露 404：单测和页面自测都看不见。
 */
const PDF_SPLIT_PREFIX = '/api/v1/pdf-splitting'

const pdfSplitApi = createApiClient({ prefix: PDF_SPLIT_PREFIX })

/** GET /pdf-splitting/jobs/{job_id} 的响应（生成物 PdfSplitJobOut）。
 *  后端已修复 OpenAPI 组件名冲突（此前该端点误挂 doc-converter 的 JobOut，
 *  缺 job_id / segments 字段），schema 与实际响应一致，直接取生成物。 */
type PdfSplitJobPayload = components['schemas']['PdfSplitJobOut']

/** POST /pdf-splitting/jobs 的响应（生成物 PdfSplitJobSubmitOut） */
type PdfSplitJobSubmit = components['schemas']['PdfSplitJobSubmitOut']

/** 云端解析平台偏好：auto=优先+容灾；锁定值=只用它，失败不降级。
 *
 *  `deepseek` 与前两者的区别只有一处：它的凭证在系统配置（`DEEPSEEK_OCR_API_KEY`），
 *  不在「解析平台」管理页。对前端调用方没有差别——都是发一个 `cloud_backend` 单值。 */
export type CloudBackend = 'auto' | 'mineru' | 'textin' | 'deepseek'

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
    /**
     * 分段策略：batch（分批摘要，稳）/ wholebook（整本一次，更准）/ wholebook_cross（两种都跑，分段调用翻倍）。
     * 不传则由后端按系统默认（batch）处理。
     */
    segmentStrategy?: string
    /**
     * 分歧自动裁定：两个引擎读得不一样时打分裁定「哪一侧与图上的字相符」。
     * 默认由后端取 true；**只在 ≥2 个可比对引擎时才有分歧可判**，单引擎下开着也是空转。
     */
    ocrJudgeEnabled?: boolean
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
  // 这两项是**任务级选择**（按包记住），不是运维开关：分段策略决定分段 LLM 调用次数，
  // 判定只在双引擎分歧上有事可做。不传时后端用自己的默认值（batch / 开）。
  if (opts.segmentStrategy) body.append('segment_strategy', opts.segmentStrategy)
  if (opts.ocrJudgeEnabled !== undefined) body.append('ocr_judge_enabled', opts.ocrJudgeEnabled ? '1' : '0')
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
  /** 人工转正角度编码 `页码:角度,页码:角度`（见 draft/page-rotation.ts 的 rotationsForRange） */
  rotations = '',
): Promise<Blob> {
  const body = new FormData()
  body.append('file', new File([file], name, { type: 'application/pdf' }))
  body.append('page_start', String(pageStart))
  body.append('page_end', String(pageEnd))
  // 空串不传：老后端不认这个字段，多传一个空字段只会让日志多一行噪音
  if (rotations) body.append('rotations', rotations)
  const res = await pdfSplitApi.post('extract-pages', { body, timeout: UPLOAD_TIMEOUT_MS })
  return await res.blob()
}

/**
 * 单段已切好的 PDF 直链（GET /pdf-splitting/jobs/{job_id}/segments/{segment_id}/pdf）。
 *
 * ⚠️ **不能直接当 `<a href>` 用**：JWT 存在 localStorage，只有经 ky 发的请求才带
 * `Authorization`；浏览器导航带不上它，后端也刻意不收 `?token=<JWT>`（安全审计
 * M-2：JWT 会落进 nginx access log / 浏览器历史 / Referer）。裸链接在任何账号下
 * 都是 401——这正是「用自己的账号下载自己的材料也失败」那次事故
 * （回归注释见 `inbox/components/InboxView.dom.test.tsx`）。
 *
 * 正确用法：`downloadUrl(await withDownloadTicket(segmentPdfUrl(jobId, pk)))`。
 */
export function segmentPdfUrl(jobId: string, segmentId: number, rotations = ''): string {
  const base = `${PDF_SPLIT_PREFIX}/jobs/${encodeURIComponent(jobId)}/segments/${segmentId}/pdf`
  return appendRotations(base, rotations)
}

/** 单段 Markdown 直链（GET .../segments/{segment_id}/md）。与 PDF 同一套票据换票纪律，见上 */
export function segmentMdUrl(jobId: string, segmentId: number): string {
  return `${PDF_SPLIT_PREFIX}/jobs/${encodeURIComponent(jobId)}/segments/${segmentId}/md`
}

/**
 * 打包下载直链（GET /pdf-splitting/jobs/{job_id}/download）。
 *
 * 不传 `segmentIds` = 整包（后端把该任务每一段的 pdf + md 打进一个 zip）；
 * 传了就只打这几段：`?ids=12,15`（后端收的是 `PdfSplitSegment` 主键，不是列表下标）。
 *
 * 同样**不能当 `<a href>` 用**；且这是**带 query 的 URL**，换票时 `appendTicket`
 * 会拼成 `&ticket=`（拼错成第二个 `?` 时后端只会收到一个叫 `?ids` 的垃圾参数）。
 */
export function jobDownloadUrl(jobId: string, segmentIds?: number[], rotations = ''): string {
  const ids = normalizeSegmentIds(segmentIds)
  const base = `${PDF_SPLIT_PREFIX}/jobs/${encodeURIComponent(jobId)}/download`
  const withIds = ids.length > 0 ? `${base}?ids=${ids.join(',')}` : base
  return appendRotations(withIds, rotations)
}

/**
 * 给下载直链追加旋转参数。
 *
 * ⚠️ 拼 `&` 还是 `?` 必须看已有 query：`jobDownloadUrl` 带 `ids` 时已经有一个
 * `?`，再拼第二个 `?` 后端只会收到一个叫 `?ids` 的垃圾参数（同 `appendTicket`
 * 的教训）。空串不加——URL 保持与不带旋转时**逐字相同**，日志/快照比对才有意义。
 */
function appendRotations(url: string, rotations: string): string {
  const value = rotations.trim()
  if (!value) return url
  const sep = url.includes('?') ? '&' : '?'
  return `${url}${sep}rotations=${encodeURIComponent(value)}`
}

/** 草稿导出的段（`POST /export-draft` 的 spec 项） */
export interface DraftExportSegmentIn {
  name: string
  part_index: number
  page_start: number
  page_end: number
  /** 同 extract-pages 的编码；空串不传 */
  rotations?: string
  /** 段正文（云端识别才会产生）；空则包里只出 pdf */
  md?: string
}

/**
 * 把**草稿里的段**导出成 zip（POST /pdf-splitting/export-draft）。
 *
 * 与 `jobDownloadUrl` 的分工：那条按拆分任务的段打 zip（段必须有后端产物 id）；
 * 这条按草稿打 zip —— 律师不跑自动分段、自己切页命名后也要能导出。
 *
 * `files` 的每一项会被服务端按**文件名** `part_<partIndex>.<ext>` 认领素材：
 * 用文件名当键而不是「按顺序对应」，是因为某份素材可能读不出来而少发一个，
 * 按顺序会让后面每份都错位（导出的内容和段名对不上，且几乎看不出来）。
 *
 * 返回被服务端跳过的段数（页范围越界 / 素材对不上）：由调用方提示，不静默少几份。
 */
export async function exportDraftZip(opts: {
  files: Array<{ partIndex: number; filename: string; blob: Blob }>
  segments: DraftExportSegmentIn[]
  /** 包名 → 下载文件名（缺省「材料导出」） */
  name?: string
}): Promise<{ blob: Blob; skipped: number }> {
  const body = new FormData()
  for (const file of opts.files) {
    const ext = /\.[A-Za-z0-9]{1,6}$/.exec(file.filename)?.[0] ?? (file.blob.type === 'application/pdf' ? '.pdf' : '.png')
    body.append('files', new File([file.blob], `part_${file.partIndex}${ext}`, { type: file.blob.type }))
  }
  body.append('spec', JSON.stringify({ segments: opts.segments }))
  const query = opts.name?.trim() ? `?name=${encodeURIComponent(opts.name.trim())}` : ''
  const res = await pdfSplitApi.post(`export-draft${query}`, { body, timeout: UPLOAD_TIMEOUT_MS })
  const skipped = Number(res.headers.get('X-Export-Skipped') ?? '0') || 0
  return { blob: await res.blob(), skipped }
}

/**
 * 只留**正整数**并去重排序。
 * 主键是后端自增 int：0 / 负数 / 小数 / NaN 只可能来自调用方把下标或空值当主键
 * 传进来，后端会直接 400（律师看到的是「下载失败」而不是「参数错了」）。
 * 排序 + 去重是为了让同一组选择永远拼出同一个 URL——日志和快照比对才有意义。
 */
function normalizeSegmentIds(segmentIds?: number[]): number[] {
  if (!segmentIds || segmentIds.length === 0) return []
  return [...new Set(segmentIds.filter((n) => Number.isInteger(n) && n > 0))].sort((a, b) => a - b)
}

export async function getPdfSplitJob(jobId: string): Promise<PdfSplitJobPayload> {
  return pdfSplitApi.get(`jobs/${jobId}`).json<PdfSplitJobPayload>()
}

/**
 * 归档入参里的一段（POST /pdf-splitting/jobs/{job_id}/archive-to-case-folder）。
 *
 * 两个类型字段（doc_type / material_type）后端都要，而本域一个段只有一个名字，
 * 调用方先同值传（`use-assign-launch` 的 `archiveGroupsOf`）。
 */
export interface ArchiveToCaseFolderSegment {
  page_start: number
  page_end: number
  doc_type: string
  material_type: string
  /**
   * 人工转正角度（`页码:角度,...`，页码=源 PDF 绝对页号）。
   *
   * 后端在**切页之前**把它烧进页对象，再切页与算副本指纹——所以落进卷宗的
   * 就是律师看到的方向，而不是扫描仪给的原始方向。空/缺省 = 不转。
   */
  rotations?: string
}

/** 归档结果：落在哪儿、写了哪些文件、哪些疑似副本、哪些段跳过 */
export interface ArchiveToCaseFolderResult {
  root: string
  written: Array<{ filename: string; subdir: string; is_duplicate: boolean }>
  duplicates: string[][]
  skipped: Array<{ doc_type: string; reason: string }>
  notice_path: string
}

/**
 * 归案后把这次拆分的段归档到案件文件夹（POST /pdf-splitting/jobs/{job_id}/archive-to-case-folder）。
 *
 * 归档按**拆分任务**分组：一个 job 一次请求，`segments` 是该 job 产出的那些段
 * （页区间 + 类型名）。后端的命名 / 版本对齐 / 副本识别都在服务端做，前端只给
 * 「哪几页、算什么类型」。
 *
 * 失败**直接抛**：归档是归案的附加动作，由调用方决定只提示、不让归案看起来失败
 * （见 `use-assign-launch` 的 `onAssignConfirm`）。
 */
export async function archiveSplitToCaseFolder(
  jobId: string,
  caseId: number,
  segments: ArchiveToCaseFolderSegment[],
  opts: {
    /** 归档日期（YYYY-MM-DD）；不传由后端按今天算 */
    date?: string
    /** 已存在同名文件时是否照样写入（默认由后端决定） */
    writeDuplicates?: boolean
  } = {},
): Promise<ArchiveToCaseFolderResult> {
  return pdfSplitApi
    .post(`jobs/${jobId}/archive-to-case-folder`, {
      json: {
        case_id: caseId,
        segments,
        // 可选字段只在调用方给了才进 body：后端按缺省处理，别用 undefined 占位
        ...(opts.date ? { date: opts.date } : {}),
        ...(opts.writeDuplicates !== undefined ? { write_duplicates: opts.writeDuplicates } : {}),
      },
    })
    .json<ArchiveToCaseFolderResult>()
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
