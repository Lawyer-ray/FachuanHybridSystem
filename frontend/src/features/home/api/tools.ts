import { createApiClient } from '@/lib/api'
import type { ConvertTemplate } from '../types'

/** 快捷工具资源：法院短信、要素式转换、DOC→DOCX。 */

export const automationApi = createApiClient({ prefix: '/api/v1/automation' })
export const docConvertApi = createApiClient({ prefix: '/api/v1/doc-convert' })
export const docConverterApi = createApiClient({ prefix: '/api/v1/doc-converter' })

/** 收法院短信：POST /automation/court-sms，返回状态由轮询/列表体现 */
export async function submitCourtSms(content: string): Promise<void> {
  await automationApi.post('court-sms', { json: { content } })
}

export interface ConvertTemplateGroup {
  category: string
  items: ConvertTemplate[]
}

/** 模板列表 query key（DocConvertCard 订阅） */
export const CONVERT_TEMPLATES_KEY = ['doc-convert-templates'] as const

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
  const filename = matched?.[1]
    ? decodeURIComponent(matched[1])
    : `${file.name.replace(/\.[^.]+$/, '')}-要素式.docx`
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
  const res = await docConverterApi.post('jobs', { body }).json<{ job_id?: string; success?: boolean; message?: string }>()
  // 业务失败兜底：后端若返回 200 + success:false（或异常缺 job_id），别拿 undefined 去轮询
  if (res.success === false || !res.job_id) {
    throw new Error(res.message || '创建转换任务失败')
  }
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
