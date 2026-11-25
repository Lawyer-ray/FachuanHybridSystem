import { createApiClient } from '@/lib/api'

import type { FolderOwnerKind } from '../../api'

/**
 * 文档工作面（审查 / 版本）的接口封装。
 *
 * **所有接口都以「文件夹里的那一份文件」为坐标**（kind + owner_id + subpath），
 * 不带 task_id——审查不再是一次上传产生的一份新文档，而是挂在原文件上的一次动作。
 *
 * 延迟创建客户端：App 级测试会整体加载本模块，mock 的 `@/lib/api` 未必带
 * `createApiClient`（与 `onlyoffice/api.ts` 同一处理）。
 */
let _api: ReturnType<typeof createApiClient> | null = null
function docApi() {
  _api ??= createApiClient({ prefix: '/api/v1/doc-workspace' })
  return _api
}

export type Severity = 'high' | 'medium' | 'low'
export type Verdict = 'compliant' | 'deviation' | 'missing' | 'not_applicable'
export type Delivery = 'revision' | 'comment' | 'both' | 'list_only'
export type FindingStatus = 'proposed' | 'accepted' | 'rejected' | 'stale' | 'moot' | 'merged' | 'unanchored'
export type RunStatus = 'none' | 'queued' | 'running' | 'done' | 'failed' | 'superseded'

export interface FindingItem {
  id: number
  ordinal: number
  verdict: Verdict
  severity: Severity
  kind: string
  clause_type: string
  rule_key: string
  legal_basis: string
  quote: string
  title: string
  reason: string
  suggestion_original: string
  suggestion_replacement: string
  suggestion_note: string
  delivery: Delivery
  status: FindingStatus
  reject_reason_code: string
  reject_note: string
  docx_rev_ids: number[]
  comment_ids: number[]
}

export interface ReviewRunPayload {
  id: number
  owner_kind: string
  owner_id: number
  subpath: string
  stance: string
  contract_type: string
  status: RunStatus
  playbook_key: string
  playbook_version: number | null
  summary: Record<string, unknown>
  error_message: string
  created_at: string
  finished_at: string | null
  findings: FindingItem[]
}

export interface SnapshotItem {
  seq: number
  sha256: string
  size: number
  reason: string
  actor_kind: string
  actor_id: number | null
  created_at: string
}

/** 驳回理由码：**必须选码**，自由文本没法统计误报率。 */
export const REJECT_REASONS: { value: string; label: string }[] = [
  { value: 'commercial', label: '商业让步' },
  { value: 'jurisdiction', label: '法域不适' },
  { value: 'already_covered', label: '已被其他条款覆盖' },
  { value: 'false_positive', label: '误报' },
  { value: 'client_refused', label: '客户明确拒绝' },
  { value: 'other', label: '其他' },
]

export const SEVERITY_LABEL: Record<Severity, string> = { high: '高', medium: '中', low: '低' }
export const DELIVERY_LABEL: Record<Delivery, string> = {
  revision: '修订',
  comment: '批注',
  both: '修订+批注',
  list_only: '仅清单',
}
export const STATUS_LABEL: Record<FindingStatus, string> = {
  proposed: '待决',
  accepted: '已采纳',
  rejected: '已驳回',
  stale: '锚点失效',
  moot: '已消解',
  merged: '已合并',
  unanchored: '锚不到',
}

function base(kind: FolderOwnerKind, ownerId: number, subpath: string) {
  return { kind, owner_id: ownerId, subpath }
}

function qsOf(kind: FolderOwnerKind, ownerId: number, subpath: string): string {
  return new URLSearchParams({ kind, owner_id: String(ownerId), subpath }).toString()
}

/** 最近一轮审查（含清单）。没有跑过时 `status` 为 `none`。 */
export async function fetchLatestRun(
  kind: FolderOwnerKind,
  ownerId: number,
  subpath: string,
): Promise<ReviewRunPayload> {
  return docApi().get(`review/runs/latest?${qsOf(kind, ownerId, subpath)}`).json<ReviewRunPayload>()
}

/** 发起审查。立刻返回 run_id，执行在后台（轮询 `fetchRun` 看进度）。 */
export async function startReview(
  kind: FolderOwnerKind,
  ownerId: number,
  subpath: string,
  opts: { stance?: string; contract_type?: string } = {},
): Promise<{ run_id: number; status: RunStatus; queued: boolean; hint: string }> {
  return docApi()
    .post('review/runs', {
      json: { ...base(kind, ownerId, subpath), stance: opts.stance ?? 'neutral', contract_type: opts.contract_type ?? '' },
    })
    .json()
}

export async function fetchRun(runId: number): Promise<ReviewRunPayload> {
  return docApi().get(`review/runs/${runId}`).json<ReviewRunPayload>()
}

export interface DecideResult {
  ok: boolean
  status: string
  reason: string
  stale: boolean
  rev_ids: number[]
  comment_ids: number[]
}

/** 逐条决策。`accept` 会**真的改文件**（修订 / 批注）。 */
export async function decideFinding(
  findingId: number,
  action: 'accept' | 'reject' | 'moot' | 'stale',
  opts: { reasonCode?: string; note?: string } = {},
): Promise<DecideResult> {
  return docApi()
    .post(`review/findings/${findingId}/decide`, {
      json: { action, reason_code: opts.reasonCode ?? '', note: opts.note ?? '' },
    })
    .json<DecideResult>()
}

/** 批量采纳。**必须 confirm**：落笔即写文件，撤销要走版本回滚。 */
export async function bulkAccept(
  runId: number,
  opts: { severity?: Severity | ''; kinds?: string[] } = {},
): Promise<{ accepted: number; stale: number; failed: number; details: { id: number; applied: boolean; reason: string }[] }> {
  return docApi()
    .post(`review/runs/${runId}/bulk-accept`, {
      json: { severity: opts.severity ?? '', kinds: opts.kinds ?? [], confirm: true },
    })
    .json()
}

export async function fetchReport(runId: number): Promise<{ markdown: string }> {
  return docApi().post(`review/runs/${runId}/report`, { json: {} }).json<{ markdown: string }>()
}

export async function listSnapshots(
  kind: FolderOwnerKind,
  ownerId: number,
  subpath: string,
): Promise<{ items: SnapshotItem[] }> {
  return docApi().get(`snapshots?${qsOf(kind, ownerId, subpath)}`).json<{ items: SnapshotItem[] }>()
}

/** 回滚到某一版。回滚动作本身也会留一版（`previous_seq` 可再滚回来）。 */
export async function restoreSnapshot(
  kind: FolderOwnerKind,
  ownerId: number,
  subpath: string,
  seq: number,
): Promise<{ restored: boolean; reason: string; seq: number; sha256: string; previous_seq: number }> {
  return docApi()
    .post('snapshots/restore', { json: { ...base(kind, ownerId, subpath), seq } })
    .json()
}

export const SNAPSHOT_REASON_LABEL: Record<string, string> = {
  editor_save: '编辑器保存',
  ai_rewrite: 'AI 改写',
  ai_review_apply: 'AI 审查落笔',
  restore: '回滚',
}

export const REJECT_REASON_LABEL: Record<string, string> = Object.fromEntries(
  REJECT_REASONS.map((r) => [r.value, r.label]),
)
