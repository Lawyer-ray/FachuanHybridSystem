import { EXCLUDED_LABELS, formatAmount, KIND_STYLES } from './constants'
import type { Intake, IntakeCandidate, SelectableContract } from './types'

/**
 * 到账待认领的纯领域逻辑（无 React、无 IO），供组件与单测共用。
 */

/** 卡片主状态：决定整条卡片的提示色与动作按钮。
 *
 * - `matched`：有实名命中的候选 → 可直接确认；
 * - `amountOnly`：**只有金额撞车**，无身份证据 → 必须强提醒人工核对；
 * - `unmatched`：没有任何候选 → 让人自己从下拉里选。
 */
export type IntakeShape = 'matched' | 'amountOnly' | 'unmatched'

export function intakeShape(intake: Intake): IntakeShape {
  const top = intake.candidates[0]
  if (!top) return 'unmatched'
  if (top.kind === 'amount_only') return 'amountOnly'
  return 'matched'
}

/** 是否有可以「一键采纳」的系统建议（只认实名命中的建议）。
 *
 * 后端对 amount_only 的候选不会预选建议（suggested_contract_id 为 null），
 * 这里再兜一层：即使后端给了，只要 kind 是 amount_only 也不显示"确认建议"按钮，
 * 避免暗示用户直接点。
 */
export function hasUsableSuggestion(intake: Intake): boolean {
  if (intake.suggested_contract_id == null) return false
  const top = intake.candidates[0]
  return top != null && top.kind !== 'amount_only'
}

/** 卡片顶部的一句话结论 */
export function intakeHeadline(intake: Intake): string {
  const shape = intakeShape(intake)
  const top = intake.candidates[0]
  if (shape === 'unmatched' || top == null) return '未匹配到在办项目，请手动选择'
  if (shape === 'amountOnly') return '仅有金额吻合，请核对后选择'
  return `${KIND_STYLES[top.kind].label}：${top.contract_name}`
}

/** 金额展示（含币种） */
export function amountText(intake: Intake): string {
  return formatAmount(intake.amount)
}

/** 被排除线索的一行文案：`费用已收齐（50000/50000）…` */
export function hintText(hint: { excluded_by: string; note: string; contract_name: string }): string {
  const label = EXCLUDED_LABELS[hint.excluded_by] ?? hint.excluded_by
  // 后端的 note 已经带了人话说明（含金额对比），优先用它；没有则退回标签
  const detail = hint.note && hint.note !== label ? hint.note : label
  return detail
}

/** 候选的一行理由（拼给用户看"为什么推荐它"） */
export function candidateReason(candidate: IntakeCandidate): string {
  return candidate.reasons[0] ?? ''
}

/** 下拉项目的右侧说明：还能收多少 / 已到期 */
export function contractHint(contract: SelectableContract): string {
  const parts: string[] = []
  if (contract.outstanding_amount != null) {
    parts.push(`应收余额 ${formatAmount(contract.outstanding_amount)}`)
  }
  if (contract.expires_note) parts.push(contract.expires_note)
  return parts.join(' · ')
}

/** 前端过滤下拉项（后端已按名称搜过，这里再兜一层用于本地即时筛选） */
export function filterContracts(rows: SelectableContract[], keyword: string): SelectableContract[] {
  const term = keyword.trim()
  if (!term) return rows
  return rows.filter((c) => c.name.includes(term))
}
