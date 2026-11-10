import { formatAmount, MATCH_KIND_STYLES } from './constants'
import type { InvoiceIntake } from './types'

/**
 * 发票待认领的纯领域逻辑（无 React、无 IO），供组件与单测共用。
 */

/** 结论行里案由片段的截断长度：侧栏窄，超过这个长度必然被截掉 */
const REASON_MAX = 30

/**
 * 全部候选里最高等级的匹配信号。
 *
 * 候选已按分数排序，但仍显式挑最高档：`party_name` 的分数可能高于
 * `case_text`（同一个购买方名字出现两次时），而「凭什么是这么想的」应由
 * 信号等级回答，不是分数。
 */
export function topKind(intake: InvoiceIntake) {
  // 防御性取数：后端 schema 若漏字段，这里崩会让整张卡被 ErrorBoundary 换掉
  const kinds = (intake.candidates ?? []).map((c) => c.kind)
  if (kinds.includes('project_code')) return 'project_code' as const
  if (kinds.includes('case_text')) return 'case_text' as const
  if (kinds.includes('party_name')) return 'party_name' as const
  return null
}

/**
 * 卡片结论：一句话说清「系统认为这张票该绑哪个项目」。
 *
 * 有建议 → `✓ 确定性匹配：合同名`；没有 → 明说需要人工选择（不给假的确定感）。
 */
export function invoiceHeadline(intake: InvoiceIntake): string {
  if (intake.suggested_contract_id == null) return '无可匹配的在办项目，需人工选择'
  const kind = topKind(intake)
  const label = kind ? MATCH_KIND_STYLES[kind].label : '系统建议'
  return `✓ ${label}：${intake.suggested_contract_name ?? '未命名项目'}`
}

/**
 * 从备注栏原文里提取案由片段。
 *
 * 备注栏的真实形态是 `2025GZM0001-张某与某公司合同纠纷`：项目号在前、, // privacy-allow 虚构样例，非真实项目号
 * 案由在后用 `-` 连接。剥掉项目号后剩下的才是人一眼能读的案由文字。
 * 超过 {@link REASON_MAX} 字截断加省略号（侧栏一行放不下）。
 */
function reasonExcerpt(intake: InvoiceIntake): string {
  const code = intake.project_code.trim()
  let text = intake.remark.trim()
  if (code && text.startsWith(code)) {
    text = text.slice(code.length).replace(/^[\s\-—_:：]+/, '')
  }
  return text.length > REASON_MAX ? `${text.slice(0, REASON_MAX)}…` : text
}

/** 卡片第二行：`购买方 · 案由片段`（两者任一为空时不留多余分隔符） */
export function invoiceSubtitle(intake: InvoiceIntake): string {
  const buyer = intake.buyer_name.trim()
  const reason = reasonExcerpt(intake)
  return [buyer, reason].filter((part) => part !== '').join(' · ')
}

/**
 * 是否有可以「一键采纳」的系统建议。
 *
 * 后端对没有合格候选的发票不会预选建议（`suggested_contract_id` 为 null），
 * 这里只认这一个判据——发票的候选全部等于 `suggested_contract`，
 * 不存在款项那边「候选是 amount_only 但建议非空」的分裂态。
 */
export function hasUsableSuggestion(intake: InvoiceIntake): boolean {
  return intake.suggested_contract_id != null
}

/** 能不能直接点「确认绑定」：待确认状态 + 有系统建议 */
export function canConfirm(intake: InvoiceIntake): boolean {
  return intake.status === 'pending' && hasUsableSuggestion(intake)
}

/** 金额展示（含币种）；识别失败没有金额时给占位而不是 `¥` */
export function amountText(intake: InvoiceIntake): string {
  if (intake.total_amount == null || intake.total_amount === '') return '金额未识别'
  return formatAmount(intake.total_amount)
}
