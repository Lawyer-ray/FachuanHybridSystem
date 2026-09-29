import { createApiClient } from '@/lib/api'
import type { ConvertTemplate } from '../types'
import { withAuthToken } from './download'

/** 快捷工具资源：法院短信、要素式转换、DOC→DOCX。 */

export const automationApi = createApiClient({ prefix: '/api/v1/automation' })
export const docConvertApi = createApiClient({ prefix: '/api/v1/doc-convert' })
export const docConverterApi = createApiClient({ prefix: '/api/v1/doc-converter' })

/**
 * 收法院短信：POST /automation/court-sms。返回新建短信记录的 id，
 * 调用方拿它轮询 GET court-sms/{id} 跟踪处理进度（弹窗动画用）。
 */
export async function submitCourtSms(content: string): Promise<number> {
  const res = await automationApi
    .post('court-sms', { json: { content } })
    .json<{ success?: boolean; message?: string; data?: { id?: number } }>()
  // 业务失败兜底：后端 200 + success:false 或缺 id 时，别拿 undefined 去轮询
  if (res.success === false || !res.data?.id) {
    throw new Error(res.message || '短信提交失败')
  }
  return res.data.id
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
  /** 转换产物（docx 二进制）。存 blob 而不是 objectURL：弹窗里可反复生成链接重下，不会过期失效 */
  blob: Blob
  filename: string
}

/** 要素式转换超时：后端 httpx 客户端是 60s，前端多等一会儿再放弃，别抢在后端前面断 */
export const DOC_CONVERT_TIMEOUT_MS = 90_000

/**
 * 要素式转换：multipart 传 file + mbid，返回转换后文书。
 * 注意：响应是二进制（docx），以 blob 取回，由调用方在点击下载时再生成 objectURL。
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
  return { blob, filename }
}

/**
 * DOC 转 DOCX 任务快照。
 * 对应后端 JobProgressOut：{ job: JobOut, items: ItemOut[] }——items 供完成弹窗
 * 展示文件明细（单件复制/下载）。
 */
export interface ConverterItem {
  id: string
  /** 展示名（原始文件名换成 .docx 后缀，与下载产物一致） */
  name: string
  /** 转换成功才有下载地址 */
  ok: boolean
  downloadUrl: string
}

export interface ConverterJob {
  jobId: string
  status: string
  total: number
  done: number
  failed: number
  items: ConverterItem[]
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

/** 查转换进度（后端返回 { job: {...}, items: [...] }） */
export async function getConverterJob(jobId: string): Promise<ConverterJob> {
  const res = await docConverterApi.get(`jobs/${jobId}`).json<{ job?: Record<string, unknown>; items?: Record<string, unknown>[] }>()
  const j = res.job ?? {}
  const items: ConverterItem[] = (res.items ?? []).map((raw) => {
    const original = typeof raw.original_name === 'string' ? raw.original_name : '未命名'
    const url = typeof raw.download_url === 'string' ? raw.download_url : ''
    return {
      id: String(raw.id ?? ''),
      name: `${original.replace(/\.[^.]+$/, '')}.docx`,
      ok: url !== '',
      downloadUrl: url,
    }
  })
  return {
    jobId,
    status: String(j.status ?? 'pending'),
    total: Number(j.total_files ?? 0),
    done: Number(j.converted_files ?? 0),
    failed: Number(j.failed_files ?? 0),
    items,
  }
}

/** 转换完成后的 ZIP 下载地址（带 token 供 <a> 直链下载） */
export function converterDownloadUrl(jobId: string): string {
  return withAuthToken(`/api/v1/doc-converter/jobs/${jobId}/download`)
}

/** 单件转换产物下载地址（带 token） */
export function converterItemDownloadUrl(jobId: string, itemId: string): string {
  return withAuthToken(`/api/v1/doc-converter/jobs/${jobId}/items/${itemId}/download`)
}

// ---------------------------------------------------------------------------
// 历史记录（DOC 转 DOCX 任务 / 要素式转换记录）
// ---------------------------------------------------------------------------

/** DOC 转 DOCX 历史任务列表项 */
export interface ConverterJobItem {
  id: string
  status: string
  total: number
  done: number
  failed: number
  hasZip: boolean
  createdAt: string
}

/** 分页列出历史转换任务（最新在前） */
export async function listConverterJobs(
  page = 1,
): Promise<{ items: ConverterJobItem[]; count: number; page: number; num_pages: number }> {
  const res = await docConverterApi
    .get('jobs', { searchParams: { page: String(page) } })
    .json<{ items: Record<string, unknown>[]; count: number; page: number; num_pages: number }>()
  return {
    items: res.items.map((j) => ({
      id: String(j.id ?? ''),
      status: String(j.status ?? 'pending'),
      total: Number(j.total_files ?? 0),
      done: Number(j.converted_files ?? 0),
      failed: Number(j.failed_files ?? 0),
      hasZip: typeof j.download_url === 'string' && j.download_url !== '',
      createdAt: String(j.created_at ?? ''),
    })),
    count: res.count,
    page: res.page,
    num_pages: res.num_pages,
  }
}

/** 要素式转换历史记录项 */
export interface ConvertRecordItem {
  id: number
  original_name: string
  mbid: string
  mbid_name: string
  status: string
  error_message: string | null
  has_file: boolean
  created_at: string
}

/** 分页列出要素式转换历史（最新在前）；status 可筛 success/failed */
export async function listConvertRecords(
  status?: string,
  page = 1,
): Promise<{ items: ConvertRecordItem[]; count: number; page: number; num_pages: number }> {
  return docConvertApi
    .get('records', { searchParams: { ...(status ? { status } : {}), page: String(page) } })
    .json<{ items: ConvertRecordItem[]; count: number; page: number; num_pages: number }>()
}

/** 要素式历史产物下载地址（带 token） */
export function convertRecordDownloadUrl(recordId: number): string {
  return withAuthToken(`/api/v1/doc-convert/records/${recordId}/download`)
}

/** 删除一条要素式转换记录（产物文件随之后端清理） */
export async function deleteConvertRecord(recordId: number): Promise<void> {
  await docConvertApi.delete(`records/${recordId}`)
}

/**
 * 复制转换产物到**系统**剪贴板（后端 NSPasteboard 写 file-url，同 Finder ⌘C）。
 * 后端非 macOS 时返回 reason=unsupported，调用方降级复制文件名。
 */
export async function copyConverterItemsToClipboard(
  jobId: string,
  itemIds: string[],
): Promise<{ success: boolean; copied: number; reason: string | null }> {
  const res = await docConverterApi
    .post(`jobs/${jobId}/items/copy-to-clipboard`, { json: { item_ids: itemIds } })
    .json<{ success?: boolean; copied?: number; reason?: string; message?: string }>()
  if (res.success === undefined && res.message) throw new Error(res.message)
  return { success: res.success === true, copied: Number(res.copied ?? 0), reason: res.reason ?? null }
}
