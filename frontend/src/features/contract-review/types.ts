/**
 * 合同复审工作台数据模型。
 *
 * 与后端 `apps/contract_review` 对齐：审查任务（ReviewTask）产出一批
 * 修订（ReviewRevision），律师逐条采纳/驳回后再定稿。
 */

/** 修订类型：错别字 / 风险条款 / 格式 */
export type RevisionKind = 'typo' | 'risk' | 'format'

/** 风险等级 */
export type RevisionSeverity = 'high' | 'medium' | 'low' | ''

/** 律师决策状态 */
export type RevisionStatus = 'pending' | 'accepted' | 'rejected'

/** 单条修订（左栏一条建议） */
export interface ReviewRevision {
  id: string
  ordinal: number
  kind: RevisionKind
  severity: RevisionSeverity
  title: string
  /** 原文（文档里要删掉的部分） */
  original: string
  /** 建议改为 */
  suggested: string
  /** 依据 / 理由（含法条） */
  reason: string
  /** 段落索引，-1 表示未能定位 */
  paragraph_index: number
  status: RevisionStatus
  reject_reason: string
}

/** 修订清单响应 */
export interface RevisionList {
  task_id: string
  total: number
  pending: number
  accepted: number
  rejected: number
  items: ReviewRevision[]
}

/** 决策动作 */
export type ResolveAction = 'accept' | 'reject' | 'reset'

/** 决策响应（字段名与后端 ResolveRevisionOut 对齐：revision_id 不是 id） */
export interface ResolveResult {
  revision_id: string
  status: RevisionStatus
  pending: number
}

/**
 * 文档内容版本：画布该不该重载。
 *
 * `content_version` 直接喂 OfficeView 的 version：采纳只改 DB 状态、不写 docx，
 * 所以值不变（不重建）；只有编辑器保存回写后 saved_version 变了才整篇重载。
 */
export interface ContentVersion {
  content_version: string
  saved_version: number
  output_file: string
}

/** 编辑器模式：只看 / 锁定修订 / 完全编辑 */
export type ReviewEditorMode = 'view' | 'review' | 'edit'

/** 版本来源：客户来稿 / AI 修订版 / 律师编辑版 / 客户回稿 */
export type VersionKind = 'original' | 'ai' | 'lawyer' | 'client'

/**
 * 版本链上的一个节点。
 *
 * 版本信息过去只活在文件名（`[修订版]V1_日期`）里：改名就断链、排序只对
 * 同一天有效。后端把它变成真实关系（parent 指向改自的那版）。
 */
export interface DocumentVersion {
  id: string
  version_no: number
  kind: VersionKind
  kind_label: string
  file_name: string
  file_path: string
  author: string
  note: string
  parent_id: string | null
  created_at: string | null
}

export interface VersionChain {
  task_id: string
  total: number
  items: DocumentVersion[]
}

/* ============================================================
 * 划词直改（direct-edit）
 *
 * 注意与上面「任务式审查」的类型区分：这里没有 task_id、没有等级、
 * 没有 revision 决策流。一次改写就是「选区 + 指令 → 若干候选 → 挑一条」。
 * ============================================================ */

/** 一条改写候选 */
export interface DirectEditCandidate {
  suggested: string
  reason: string
}

export interface DirectEditSuggestResult {
  candidates: DirectEditCandidate[]
  context_before: string
  context_after: string
}

export interface DirectEditApplyResult {
  applied: boolean
  subpath: string
  name: string
  reason: string
}
