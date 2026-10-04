import { createApiClient } from '@/lib/api'
import type { components } from '@/types/api-schema'

/**
 * 文档解析 API（对接后端 apps/document_parsing）。
 *
 * 真实路径（已用 curl 探活 + 真 PDF 实测同步/异步两条路径）：
 *   - 解析文档 = POST /document-parsing/parse      （multipart：file + 表单字段）
 *   - 查任务   = GET  /document-parsing/task/{task_id}
 *
 * 两条执行路径（由后端按 engine 的 requires_async_execution 决定，前端不判断）：
 *   - 云端后端（mineru / textin，auto 会解析成二者之一）：立即返回 task_id + status=pending，
 *     前端轮询 task 端点直到 success / failure。
 *   - 本地后端（local）：同步执行，直接在 parse 响应里返回 markdown / text。
 * 因此 parseDocument 的返回要同时承载「异步 task_id」与「同步结果」两种情况。
 */

export const documentParsingApi = createApiClient({ prefix: '/api/v1/document-parsing' })

/** 解析后端：auto 由后端挑最高优先级启用平台（mineru / textin） */
export type ParseBackend = 'auto' | 'mineru' | 'textin' | 'local'

/** 引擎展示元数据（name/说明 直接对齐后台 workbench 的选项） */
export const PARSE_BACKENDS: { value: ParseBackend; label: string; desc: string }[] = [
  { value: 'auto', label: '自动', desc: '后端挑最高优先级启用平台' },
  { value: 'mineru', label: 'MinerU', desc: 'VLM 视觉模型，擅长版面与复杂表格' },
  { value: 'textin', label: 'TextinParse', desc: '格式更广（OFD/RTF/HTML/CSV），含标题树' },
  { value: 'local', label: '本地', desc: 'PyMuPDF + RapidOCR，无网络依赖，仅 PDF/图片' },
]

/**
 * 解析提交超时：云端上传 + 排队 + 解析可能几分钟，给足 5 分钟。
 * 本地后端同步返回，用不满这个值。mineru/textin 的 HTTP 上传本身在 submit_task 里异步化，
 * 所以这个超时实际只覆盖「把任务塞进队列」这一步，但保持宽裕以防同步回退路径。
 */
export const DOC_PARSE_TIMEOUT_MS = 300_000

/** 单次任务轮询间隔：云端解析通常 5-30 秒，2 秒一轮足够灵敏又不打爆后端 */
export const DOC_PARSE_POLL_MS = 2000

/** 轮询安全上限（轮数）：5 分钟无结果就停，避免异常任务把轮询挂死 */
export const DOC_PARSE_MAX_POLLS = 150

/**
 * 解析成功的产出（submit 同步路径与 task 轮询成功路径字段一致）。
 * 手写保留：前端归一化形状（ok / method 等），非后端响应原文。
 */
export interface ParseOutcome {
  ok: boolean
  markdown: string
  text: string
  /** 解析方法：如 pymupdf / mineru / textin */
  method: string | null
  error: string | null
  metadata: Record<string, unknown>
}

/** parse 提交的即时返回：要么是同步结果，要么是待轮询的 task_id（前端归一化形状） */
export interface ParseSubmit {
  /** 有 task_id 表示异步云端解析，需轮询 getParseTaskTask */
  taskId: string | null
  status: string
  /** 同步路径下已就绪的结果；异步路径为 null */
  outcome: ParseOutcome | null
}

/** 轮询到的任务状态（前端归一化形状：not_found 为前端补充的缺态语义） */
export interface ParseTaskStatus {
  taskId: string
  status: 'pending' | 'running' | 'success' | 'failure' | 'not_found'
  /** 终态（success/failure）下的结果；中间态为 null */
  outcome: ParseOutcome | null
}

/** 任务状态白名单：后端 tasking 实际产出的四态 + 前端补充的 not_found 缺态。
 *  生成物 TaskStatusResponse.status 是裸 string，白名单校验后收窄，不做 as 直转。 */
const TASK_STATUSES = ['pending', 'running', 'success', 'failure', 'not_found'] as const

function isTaskStatus(v: string): v is (typeof TASK_STATUSES)[number] {
  return (TASK_STATUSES as readonly string[]).includes(v)
}

/**
 * 解析提交的表单形状。手写保留：字段名是前端 camelCase（submit 时拆成后端
 * upload_view 的 backend / extract_tables / … 表单键），非 wire 形状。
 */
export interface ParseDocumentIn {
  backend: ParseBackend
  extractTables: boolean
  extractImages: boolean
  returnMarkdown: boolean
}

/** toOutcome 可接受的来源字段（ParseDocumentResponse 的子集；task 端点的 result dict 也按它断言）。
 *  用 type 而非 interface：保留隐式索引签名，task 端点的裸 dict 才能 as 到这里 */
type OutcomeSource = {
  success?: boolean | null
  markdown?: string | null
  text?: string | null
  parse_method?: string | null
  error?: string | null
  metadata?: Record<string, unknown> | null
}

/** 把后端 result dict（success 时 {success,text,markdown,...}，失败时 {success:false,error}）归一化 */
function toOutcome(src: OutcomeSource): ParseOutcome {
  const ok = src.success !== false
  return {
    ok,
    markdown: typeof src.markdown === 'string' ? src.markdown : '',
    text: typeof src.text === 'string' ? src.text : '',
    method: src.parse_method == null ? null : String(src.parse_method),
    error: ok ? null : src.error == null ? '解析失败' : String(src.error),
    metadata: src.metadata && typeof src.metadata === 'object' ? src.metadata : {},
  }
}

/**
 * 解析文档：multipart 提交 file + 表单字段（与后端 admin upload_view 同款字段名）。
 * 返回交由调用方判断：taskId 非空 → 轮询；outcome 非空 → 直接展示。
 */
export async function parseDocument(file: File, opts: ParseDocumentIn): Promise<ParseSubmit> {
  const body = new FormData()
  body.append('file', file, file.name)
  body.append('backend', opts.backend)
  body.append('extract_tables', String(opts.extractTables))
  body.append('extract_images', String(opts.extractImages))
  body.append('return_markdown', String(opts.returnMarkdown))
  const res = await documentParsingApi
    .post('parse', { body, timeout: DOC_PARSE_TIMEOUT_MS })
    .json<components['schemas']['ParseDocumentResponse']>()

  const taskId = res.task_id === null || res.task_id === undefined ? null : String(res.task_id)
  // 缺状态按后端 DocumentParsingTask 初始态 pending 处理（待轮询），绝不当成 completed
  const status = res.status || 'pending'
  // 同步路径：success 且无 task_id，markdown/text 直接在顶层
  if (!taskId) {
    if (res.success === false) {
      return { taskId: null, status, outcome: { ok: false, markdown: '', text: '', method: null, error: res.error == null ? '解析失败' : String(res.error), metadata: {} } }
    }
    return { taskId: null, status, outcome: toOutcome(res) }
  }
  return { taskId, status, outcome: null }
}

/** 轮询异步解析任务状态（响应为生成物 TaskStatusResponse） */
export async function getParseTaskTask(taskId: string): Promise<ParseTaskStatus> {
  const res = await documentParsingApi
    .get(`task/${encodeURIComponent(taskId)}`)
    .json<components['schemas']['TaskStatusResponse']>()
  // 缺状态按 not_found（前端补充的缺态语义，调用方按宽限逻辑处理）
  const raw = res.status || 'not_found'
  // 白名单外的未知值兜底为 pending（任务存活）：轮询侧只认 success/failure 为
  // 终态，兜底不会造成永远轮询——DOC_PARSE_MAX_POLLS 封顶后按超时收尾
  const status = isTaskStatus(raw) ? raw : 'pending'
  const rawResult = res.result
  const outcome = rawResult && typeof rawResult === 'object' ? toOutcome(rawResult) : null
  return { taskId: res.task_id || taskId, status, outcome }
}

// ---------------------------------------------------------------------------
// 历史解析记录（DocumentParsingTask 落库记录，云端异步解析才有）
// ---------------------------------------------------------------------------

/** 历史记录列表项（不含全文，列表速览用；生成物 DocumentParsingRecordOut） */
export type ParseRecordItem = components['schemas']['DocumentParsingRecordOut']

/** 历史记录详情（含全文；生成物 DocumentParsingRecordDetailOut） */
export type ParseRecordDetail = components['schemas']['DocumentParsingRecordDetailOut']

/** 分页列出历史解析记录（最新在前）；status 可筛 pending/processing/completed/failed（响应为生成物 DocumentParsingRecordListOut） */
export async function listParseRecords(
  status?: string,
  page = 1,
): Promise<{ items: ParseRecordItem[]; count: number; page: number; num_pages: number }> {
  return documentParsingApi
    .get('records', { searchParams: { ...(status ? { status } : {}), page: String(page) } })
    .json<components['schemas']['DocumentParsingRecordListOut']>()
}

/** 按 id 取解析全文（历史点开查看用） */
export async function getParseRecord(recordId: number): Promise<ParseRecordDetail> {
  return documentParsingApi.get(`records/${recordId}`).json<ParseRecordDetail>()
}
