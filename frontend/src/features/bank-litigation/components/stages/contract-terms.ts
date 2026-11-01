/**
 * ④ 文书的条款草稿逻辑（纯函数，与组件分开以便 Fast Refresh 与单测）
 *
 * 草稿只活在 ContractPanel 的 useState 里：DEMO_CONTRACT_TERMS 是共享常量，
 * 不该被律师的一次编辑污染 —— 下一份合同还从原始自动填充值起。
 */

import { DEMO_CONTRACT_TERMS, DEMO_X3_TERM_DRAFTS } from '../demo-data'

/** 一条条款的运行时状态 */
export interface TermDraft {
  value: string
  /** 律师改过就置 true，列表回显「已修改」 */
  edited: boolean
}

/** 初始草稿：值取自动填充结果，全部未改 */
export function initTermDrafts(): Record<string, TermDraft> {
  return Object.fromEntries(
    DEMO_X3_TERM_DRAFTS.map((d) => [d.clause, { value: d.value, edited: false }]),
  )
}

/** 还没定下来的条款数（自动填充标「待定」且律师没改过的） */
export function pendingTermCount(drafts: Record<string, TermDraft>): number {
  return DEMO_CONTRACT_TERMS.filter((t) => !t.filled && !drafts[t.clause]?.edited).length
}
