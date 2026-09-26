import { createApiClient } from '@/lib/api'
import type { ConvertTemplate, LprResult } from '../types'

/** 快捷工具资源：法院短信、要素式转换、DOC→DOCX、LPR 计息。 */

export const automationApi = createApiClient({ prefix: '/api/v1/automation' })
export const docConvertApi = createApiClient({ prefix: '/api/v1/doc-convert' })
export const docConverterApi = createApiClient({ prefix: '/api/v1/doc-converter' })
export const lprApi = createApiClient({ prefix: '/api/v1/lpr' })

/** 收法院短信：POST /automation/court-sms，返回状态由轮询/列表体现 */
export async function submitCourtSms(content: string): Promise<void> {
  await automationApi.post('court-sms', { json: { content } })
}

export interface ConvertTemplateGroup {
  category: string
  items: ConvertTemplate[]
}

/** 要素式转换：取文书模板（按分类分组），替代原型里写死的下拉 */
export async function listConvertTemplates(): Promise<ConvertTemplateGroup[]> {
  const res = await docConvertApi.get('mbid-list').json<{ categories: { category: string; items: ConvertTemplate[] }[] }>()
  return res.categories ?? []
}

export interface ConvertResult {
  /** 后端返回的下载地址（可能是相对路径，交给调用方拼全） */
  downloadUrl: string
  filename: string
}

/** 要素式转换超时：后端 httpx 客户端是 60s，前端多等一会儿再放弃，别抢在后端前面断 */
export const DOC_CONVERT_TIMEOUT_MS = 90_000

/**
 * 要素式转换：multipart 传 file + mbid，返回转换后文书。
 * 注意：响应是二进制（docx/blob），这里以 blob 形式取回，由调用方触发下载。
 */
export async function convertDocument(mbid: string, file: File): Promise<ConvertResult> {
  const body = new FormData()
  body.append('file', file, file.name)
  body.append('mbid', mbid)
  const res = await docConvertApi.post('convert', { body, timeout: DOC_CONVERT_TIMEOUT_MS })
  const blob = await res.blob()
  const disposition = res.headers.get('content-disposition') || ''
  const matched = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition)
  const filename = matched ? decodeURIComponent(matched[1]) : `${file.name.replace(/\.[^.]+$/, '')}-要素式.docx`
  return { downloadUrl: URL.createObjectURL(blob), filename }
}

/**
 * DOC 转 DOCX 任务快照。
 * 对应后端 JobProgressOut：{ job: JobOut, items: ItemOut[] }，我们只用 job 部分。
 */
export interface ConverterJob {
  jobId: string
  status: string
  total: number
  done: number
  failed: number
}

/** DOC 转 DOCX：提交 multipart files[]，返回任务 id（进度需轮询 getConverterJob） */
export async function createConverterJob(files: File[]): Promise<string> {
  const body = new FormData()
  for (const f of files) body.append('files', f, f.name)
  const res = await docConverterApi.post('jobs', { body }).json<{ job_id: string; status?: string }>()
  return res.job_id
}

/** 查转换进度（后端返回 { job: {...}, items: [...] }，只取 job） */
export async function getConverterJob(jobId: string): Promise<ConverterJob> {
  const res = await docConverterApi.get(`jobs/${jobId}`).json<{ job?: Record<string, unknown> }>()
  const j = res.job ?? {}
  return {
    jobId,
    status: String(j.status ?? 'pending'),
    total: Number(j.total_files ?? 0),
    done: Number(j.converted_files ?? 0),
    failed: Number(j.failed_files ?? 0),
  }
}

/** 转换完成后的下载地址（后端有独立 download 端点，返回 zip） */
export function converterDownloadUrl(jobId: string): string {
  return `/api/v1/doc-converter/jobs/${jobId}/download`
}

export interface LprCalculateIn {
  principal: number
  startDate: string
  endDate: string
  rateMode: 'lpr' | 'custom'
  /** LPR 模式：1y / 5y */
  rateType: '1y' | '5y'
  /** 自定义模式 */
  customRateValue?: number
  customRateUnit?: 'percent' | 'permille' | 'permyriad'
}

/** 分档明细概要：如「3.10% × 19 天」列表压缩成一行（最多 3 段） */
function summarizePeriods(periods: Record<string, unknown>[]): string {
  if (periods.length === 0) return ''
  const parts = periods.slice(0, 3).map((p) => `${p.rate ?? '?'}% × ${p.days ?? '?'} 天`)
  const suffix = periods.length > 3 ? ` 等 ${periods.length} 段` : ''
  return parts.join('，') + suffix
}

/** LPR 计息：后端按央行报价分档计算， periods 为分段明细 */
export async function calculateInterest(payload: LprCalculateIn): Promise<LprResult> {
  const json: Record<string, unknown> = {
    principal: payload.principal,
    start_date: payload.startDate,
    end_date: payload.endDate,
    rate_mode: payload.rateMode,
  }
  if (payload.rateMode === 'lpr') {
    json.rate_type = payload.rateType
  } else {
    json.custom_rate_value = payload.customRateValue
    json.custom_rate_unit = payload.customRateUnit ?? 'percent'
  }
  const res = await lprApi.post('calculate', { json }).json<Record<string, unknown>>()
  const periods = Array.isArray(res.periods) ? (res.periods as Record<string, unknown>[]) : []
  return {
    success: Boolean(res.success),
    totalInterest: res.total_interest == null ? '' : String(res.total_interest),
    totalDays: res.total_days == null ? null : Number(res.total_days),
    startDate: res.start_date == null ? null : String(res.start_date),
    endDate: res.end_date == null ? null : String(res.end_date),
    message: res.message == null ? null : String(res.message),
    summary: summarizePeriods(periods),
  }
}
