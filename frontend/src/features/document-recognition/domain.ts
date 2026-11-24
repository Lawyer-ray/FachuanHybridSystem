/** 纯领域逻辑：候选行归一化与不可变更新（vitest 单测点）。 */

import { ACCEPT_EXTENSIONS, MAX_FILE_MB, SOURCE_LABELS } from './constants'
import type { CaseRecommendation, ContactInfo, DateCandidate, TaskOut } from './types'
import { toLocalInputValue } from '@/lib/date'
import { withAuthToken } from '@/lib/token'

/** 文字路径（/reminders/parse）产出的候选，与识别候选共用确认 UI */
export interface ParsedCandidate {
  content: string
  reminder_type: string
  reminder_type_label: string
  due_at: string
  source_text: string
}

/** 统一候选行：识别候选（有 candidateId）与文字候选（无）都归一到这个形态 */
export interface CandidateRow {
  key: string
  /** 识别任务候选 ID；文字路径候选没有（走 /reminders/create 逐条建） */
  candidateId: number | null
  checked: boolean
  /** datetime-local 的值（naive 本地 "YYYY-MM-DDTHH:mm"），提交时原文上送 */
  dueLocal: string
  reminderType: string
  label: string
  contextText: string
  /** 文字路径的完整提醒内容（作为 content 提交） */
  content: string
  source: string
  confidence: number | null
  status: 'pending' | 'confirmed' | 'skipped'
  reminderId: number | null
  /** 后端复核标记（duplicate / discarded_by_gate 等），驱动置灰与徽标 */
  reviewFlags: string[]
  /** 后端给的起算点说明，空串表示没有可展示的推导依据 */
  anchorNote: string
  /** 后端给的推导中文标签（候选来源行的首选文案） */
  derivationLabel: string
  /** 后端算好的默认勾选；文字路径无后端，取初始勾选 true */
  defaultChecked: boolean
}

/** naive 本地值 → 展示文本 "MM-DD HH:mm" */
export function formatDueLocal(value: string): string {
  if (!value) return ''
  const [date, time] = value.split('T')
  if (!time) return date ?? ''
  const md = (date ?? '').slice(5).replace('-', '月')
  return `${md}日 ${time}`
}

/** 识别任务的候选 → 行（默认勾选只认后端 default_checked，前端不再按分数猜） */
export function rowsFromTask(task: TaskOut): CandidateRow[] {
  return (task.date_candidates ?? []).map((c: DateCandidate) => ({
    key: `c-${c.id}`,
    candidateId: c.id,
    checked: c.status === 'pending' && (c.default_checked ?? false),
    dueLocal: toLocalInputValue(c.due_at),
    reminderType: c.reminder_type,
    label: c.reminder_type_label,
    contextText: c.context_text ?? '',
    content: '',
    source: c.source,
    confidence: c.confidence ?? null,
    status: c.status,
    reminderId: c.reminder_id ?? null,
    reviewFlags: c.review_flags ?? [],
    anchorNote: c.anchor_note ?? '',
    derivationLabel: c.derivation_label ?? '',
    defaultChecked: c.default_checked ?? false,
  }))
}

/** 候选来源行：后端推导标签优先，其次提取来源中文，最后原值（空则交给调用方收起整行） */
export function candidateSourceLine(row: CandidateRow): string {
  return row.derivationLabel || SOURCE_LABELS[row.source] || row.source
}

/** 候选起算点行：后端没给起算点说明时返回空串（不渲染） */
export function candidateAnchorLine(row: CandidateRow): string {
  return row.anchorNote
}

const REVIEW_FLAG_LABELS: Record<string, string> = {
  anchor_effective: '起算点待确认',
  generic_boilerplate: '通用文书',
  low_confidence: '低置信',
  far_future: '远期日期',
  duplicate: '重复项',
  discarded_by_gate: '已过滤',
}

/** 复核标记 → 中文徽标；未知标记原样返回（后端新增标记不被吞掉） */
export function flagLabel(flag: string): string {
  return REVIEW_FLAG_LABELS[flag] ?? flag
}

/** 推荐案件自动预选：首位高分（≥80）且明显领先次位（≥15 分）时预选，
 *  用户仍可一键换选——预选只省点击，不替人做决定。 */
export function pickAutoRecommendation(recos: CaseRecommendation[]): CaseRecommendation | null {
  const first = recos[0]
  if (!first || first.score < 80) return null
  const second = recos[1]
  if (second && first.score - second.score < 15) return null
  return first
}

/** 联系人展示串："张三（0757-1234567）；李四" */
export function formatContacts(contacts: ContactInfo[]): string {
  return contacts
    .map((c) => (c.name && c.phone ? `${c.name}（${c.phone}）` : c.name || c.phone || ''))
    .filter(Boolean)
    .join('；')
}

/** 后端 media 相对链接（/media/...）→ 可渲染的绝对 URL（**不含**鉴权票据）。
 *  绝对地址原样返回；相对地址按 API base 的 origin 解析（dev 走 Vite 同源代理，
 *  生产同源部署；localStorage api_base_url 为绝对地址的宿主环境也能正确拼）。
 *
 *  需要鉴权时配合 `resolveMediaUrlWithAuth`（异步换下载票据）使用。 */
export function resolveMediaUrl(url: string | null | undefined, origin?: string): string {
  if (!url) return ''
  if (/^https?:/i.test(url)) return url
  let resolvedOrigin = origin
  if (!resolvedOrigin && typeof window !== 'undefined') {
    // import.meta.env 自定义变量类型是 any（vite/client 的索引签名），as 收窄成字符串
    const base = localStorage.getItem('api_base_url') || (import.meta.env.VITE_API_BASE_URL as string | undefined) || ''
    resolvedOrigin = base.startsWith('http') ? new URL(base).origin : window.location.origin
  }
  return resolvedOrigin ? `${resolvedOrigin}${url}` : url
}

/** resolveMediaUrl + 下载票据（安全审计 M-2：JWT 不再进 URL）。
 *  <img>/<iframe>/<a> 带不上 Authorization 头，改用 60 秒一次性票据 ?ticket=。 */
export async function resolveMediaUrlWithAuth(url: string | null | undefined, origin?: string): Promise<string> {
  const abs = resolveMediaUrl(url, origin)
  if (!abs) return ''
  return withAuthToken(abs)
}

/** 文字解析候选 → 行（全部可编辑，逐条走 /reminders/create） */
export function rowsFromParsed(parsed: ParsedCandidate[]): CandidateRow[] {
  return parsed.map((p, i) => ({
    key: `t-${i}`,
    candidateId: null,
    checked: true,
    dueLocal: toLocalInputValue(p.due_at),
    reminderType: p.reminder_type,
    label: p.reminder_type_label,
    contextText: p.source_text ?? '',
    content: p.content,
    source: 'text',
    confidence: null,
    status: 'pending',
    reminderId: null,
    reviewFlags: [],
    anchorNote: '',
    derivationLabel: '',
    defaultChecked: true,
  }))
}

/** 不可变更新一行 */
export function patchRow(rows: CandidateRow[], key: string, patch: Partial<CandidateRow>): CandidateRow[] {
  return rows.map((r) => (r.key === key ? { ...r, ...patch } : r))
}

/** 不可变合并一条行内编辑到 overrides 表（key 已存在时叠加，不覆盖其他行） */
export function patchRowWithOverride(
  prev: Record<string, Partial<CandidateRow>>,
  key: string,
  patch: Partial<CandidateRow>,
): Record<string, Partial<CandidateRow>> {
  return { ...prev, [key]: { ...(prev[key] ?? {}), ...patch } }
}

/** 待写入的行：勾选且状态为 pending（可编辑） */
export function selectedPendingRows(rows: CandidateRow[]): CandidateRow[] {
  return rows.filter((r) => r.status === 'pending' && r.checked && r.candidateId !== null)
}

/** 文字路径待创建的行：勾选且无 candidateId */
export function selectedTextRows(rows: CandidateRow[]): CandidateRow[] {
  return rows.filter((r) => r.status === 'pending' && r.checked && r.candidateId === null)
}

/** 文件校验：格式 / 大小（返回拒绝原因，null 表示通过） */
export function fileRejectReason(file: File): string | null {
  const ext = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`
  if (!ACCEPT_EXTENSIONS.split(',').includes(ext)) {
    return `不支持的格式 ${ext}，请上传 PDF 或图片`
  }
  if (file.size > MAX_FILE_MB * 1024 * 1024) {
    return `文件超过 ${MAX_FILE_MB}MB`
  }
  return null
}
