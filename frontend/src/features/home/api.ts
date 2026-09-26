import { createApiClient } from '@/lib/api'
import type { ConvertTemplate, InboxItem, LprResult } from './types'

/**
 * 首页 · 今日工作台的后端对接。
 *
 * 全部路径已按 frontend/CLAUDE.md「对接后端接口纪律」核对过后端 OpenAPI
 * （http://127.0.0.1:8002/api/v1/openapi.json）与真实返回：
 *   - 日历视图        = GET  /reminders/calendar     （合并/统计都在后端算好）
 *   - 快速记一笔解析 = POST /reminders/parse       （仅能识别"绝对日期"文本）
 *   - 新建安排       = POST /reminders/create
 *   - 待处理流入     = GET  /inbox/messages        （收件箱，按收到时间倒序）
 *   - 收法院短信     = POST /automation/court-sms
 *   - 要素式转换     = POST /doc-convert/convert   （multipart：file + mbid）
 *     模板列表       = GET  /doc-convert/mbid-list
 *   - DOC 转 DOCX   = POST /doc-converter/jobs     （multipart：files[]）
 *   - LPR 计息      = POST /lpr/calculate
 */

export const remindersApi = createApiClient({ prefix: '/api/v1/reminders' })
export const inboxApi = createApiClient({ prefix: '/api/v1/inbox' })
export const automationApi = createApiClient({ prefix: '/api/v1/automation' })
export const docConvertApi = createApiClient({ prefix: '/api/v1/doc-convert' })
export const docConverterApi = createApiClient({ prefix: '/api/v1/doc-converter' })
export const lprApi = createApiClient({ prefix: '/api/v1/lpr' })

/* ------------------------------------------------------------------ 日程 / 庭期 */

/** 日历上的一条事件（GET /reminders/calendar）。同一庭审的多条同步已由后端合并。 */
export interface CalendarEvent {
  id: number
  kind: string
  kind_label: string
  /** 主标题：后端优先取关联对象名，取不到才退回 content */
  title: string
  /** content 原文 */
  content: string
  day: string
  time: string
  time_range: string
  place: string
  person: string
  /** 真实案号（后端取自案件的 CaseNumber），如 （2026）粤0608民初8233号 */
  case_no: string
  hearing_type: string
  target_type: string
  target_name: string
  case_id: number | null
  is_today: boolean
  is_overdue: boolean
  /** 合并了几条原始 reminder（同一庭审被多次同步时 >1） */
  members: number
  member_ids: number[]
}

/** 工作台统计（后端按合并后口径算好，前端不要再自己数） */
export interface CalendarStats {
  today: number
  deadline_in_7days: number
  month_court: number
}

/** GET /reminders/calendar 的响应 */
export interface CalendarMonth {
  year: number
  month: number
  stats: CalendarStats
  /** YYYY-MM-DD → 当日事件（已合并、已排序） */
  days: Record<string, CalendarEvent[]>
}

/**
 * 取某月日历视图。合并、归一化、统计都在后端做——
 * 首页与 Django admin 日历共用同一个 service，避免两边口径不一致。
 */
export async function fetchCalendarMonth(year: number, month: number): Promise<CalendarMonth> {
  return remindersApi
    .get('calendar', { searchParams: { year, month } })
    .json<CalendarMonth>()
}

export interface ParsedReminder {
  content: string
  reminder_type: string
  reminder_type_label: string
  due_at: string
  source_text: string
}

/**
 * 用文本解析提醒。后端是规则抽取而非 LLM：需要显式日期（如「2026-09-28 09:30 …」）
 * 才能识别，相对时间（「明天」「下周五」）会返回空数组。
 */
export async function parseReminder(text: string): Promise<ParsedReminder[]> {
  const res = await remindersApi.post('parse', { json: { text } }).json<ParsedReminder[]>()
  return res ?? []
}

export interface CreateReminderIn {
  reminder_type: string
  content: string
  /** ISO 字符串，如 2026-09-28T09:30:00 */
  due_at: string
  case_id?: number | null
}

export async function createReminder(payload: CreateReminderIn): Promise<void> {
  await remindersApi.post('create', {
    json: {
      reminder_type: payload.reminder_type,
      content: payload.content,
      due_at: payload.due_at,
      case_id: payload.case_id ?? null,
    },
  })
}

/* ------------------------------------------------------------------ 待处理流入 */

/** 后端 InboxMessageOut（/inbox/messages）——只声明前端用到的字段 */
export interface InboxMessageOut {
  id: number
  source_name: string
  source_type: string
  subject: string
  sender: string
  recipient: string
  received_at: string
  has_attachments: boolean
  attachment_count: number
  status: string
  segs: number
  named: number
  pages: number
  mats: number
  types: string[]
  compose: string
  created_at: string
}

/** 取待处理流入：收件箱按收到时间倒序（后端已排序），取前 limit 条 */
export async function listInbox(limit = 6): Promise<InboxItem[]> {
  const rows = await inboxApi.get('messages').json<InboxMessageOut[]>()
  return rows.slice(0, limit).map(toInboxItem)
}

/* ------------------------------------------------------------------ 快捷工具 */

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

/* ------------------------------------------------------------------ LPR 计息 */

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

/* ------------------------------------------------------------------ 归一化 */

const INBOX_ICON: Record<string, InboxItem['kind']> = {
  court_sms: 'sms',
  court_inbox: 'mail',
  manual_upload: 'mat',
  email: 'mail',
}

/** 收件箱条目 → 待处理流入展示态（含类型、状态、操作按钮） */
function toInboxItem(m: InboxMessageOut): InboxItem {
  const kind = INBOX_ICON[m.source_type] ?? 'mat'
  const hot = kind === 'sms'
  return {
    id: m.id,
    kind,
    sourceLabel: m.source_name,
    who: m.sender,
    title: m.subject,
    at: formatRelative(m.received_at),
    status: m.status === 'todo' ? '待处理' : m.status,
    action: kind === 'mat' ? '解析' : hot ? '归案' : '打开',
    hot,
  }
}

/** received_at → 相对时间（今天 HH:mm / 昨天 HH:mm / M月D日） */
export function formatRelative(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const now = new Date()
  const sameDay = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
  const hhmm = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  if (sameDay(d, now)) return `今天 ${hhmm}`
  if (sameDay(d, yesterday)) return `昨天 ${hhmm}`
  return `${d.getMonth() + 1} 月 ${d.getDate()} 日`
}

/** 分档明细概要：如「3.10% × 19 天」列表压缩成一行（最多 3 段） */
function summarizePeriods(periods: Record<string, unknown>[]): string {
  if (periods.length === 0) return ''
  const parts = periods.slice(0, 3).map((p) => `${p.rate ?? '?'}% × ${p.days ?? '?'} 天`)
  const suffix = periods.length > 3 ? ` 等 ${periods.length} 段` : ''
  return parts.join('，') + suffix
}
