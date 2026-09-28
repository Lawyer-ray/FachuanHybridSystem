/** 纯领域逻辑：候选行归一化与不可变更新（vitest 单测点）。 */

import { ACCEPT_EXTENSIONS, MAX_FILE_MB } from './constants'
import type { DateCandidate, TaskOut } from './types'

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
}

const pad2 = (n: number) => String(n).padStart(2, '0')

/** ISO（含时区偏移或 naive）→ datetime-local 需要的本地 "YYYY-MM-DDTHH:mm" */
export function toLocalInputValue(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}T${pad2(d.getHours())}:${pad2(d.getMinutes())}`
}

/** naive 本地值 → 展示文本 "MM-DD HH:mm" */
export function formatDueLocal(value: string): string {
  if (!value) return ''
  const [date, time] = value.split('T')
  if (!time) return date ?? ''
  const md = (date ?? '').slice(5).replace('-', '月')
  return `${md}日 ${time}`
}

/** 识别任务的候选 → 行（pending 行默认勾选、可编辑） */
export function rowsFromTask(task: TaskOut): CandidateRow[] {
  return (task.date_candidates ?? []).map((c: DateCandidate) => ({
    key: `c-${c.id}`,
    candidateId: c.id,
    checked: c.status === 'pending',
    dueLocal: toLocalInputValue(c.due_at),
    reminderType: c.reminder_type,
    label: c.reminder_type_label,
    contextText: c.context_text ?? '',
    content: '',
    source: c.source,
    confidence: c.confidence,
    status: c.status,
    reminderId: c.reminder_id,
  }))
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
  }))
}

/** 不可变更新一行 */
export function patchRow(rows: CandidateRow[], key: string, patch: Partial<CandidateRow>): CandidateRow[] {
  return rows.map((r) => (r.key === key ? { ...r, ...patch } : r))
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
