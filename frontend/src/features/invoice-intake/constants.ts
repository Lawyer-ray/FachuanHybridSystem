import type { InvoiceMatchKind, PaymentPickConfidence } from './types'

/**
 * 发票待认领的文案与配色常量。
 *
 * 配色只用 `index.css` 里的语义令牌（status-green / status-yellow / secondary），
 * 不自创色值——暗色模式由令牌自身切换，写死 hex 会在暗色下变成一片糊。
 */

/**
 * 匹配信号等级的含义与颜色。
 *
 * 三档的可信度是**递减**的，必须让人一眼分清「确定性」和「只是猜」：
 * - project_code：备注栏里写了律所项目号（如 `2025GZM0001`）—— 确定性匹配，可直接确认；, // privacy-allow 虚构样例，非真实项目号
 * - case_text：备注栏案由文字命中项目名 —— 通常也对，但措辞会飘，需扫一眼；
 * - party_name：只有购买方名字撞上 —— 同名/关联方很常见，最容易错。
 */
export interface MatchKindStyle {
  label: string
  /** 主文案颜色（Tailwind 类） */
  tone: string
  /** 底色 + 边框 */
  chip: string
  /** 是否需要在卡片上强提醒 */
  risky: boolean
}

export const MATCH_KIND_STYLES: Record<InvoiceMatchKind, MatchKindStyle> = {
  project_code: {
    label: '确定性匹配',
    tone: 'text-status-green',
    chip: 'border-status-green/30 bg-status-green-bg text-status-green',
    risky: false,
  },
  // 案由文字：措辞可能不完全一致，用黄色而非绿色，避免暗示「已经确定」
  case_text: {
    label: '案由匹配',
    tone: 'text-status-yellow',
    chip: 'border-status-yellow/30 bg-status-yellow-bg text-status-yellow',
    risky: false,
  },
  party_name: {
    label: '当事人匹配',
    tone: 'text-status-yellow',
    chip: 'border-status-yellow/30 bg-status-yellow-bg text-status-yellow',
    risky: true,
  },
}

/** 预选收款确定性的提示文案（只在 payment_pick_confidence 非空时展示） */
export const PAYMENT_PICK_LABELS: Record<PaymentPickConfidence, string> = {
  exact: '已预选收款',
  amount_mismatch: '金额与收款不符',
  ambiguous: '多笔收款，请自选',
  no_payment: '先开票后付款',
  red_offset: '红字发票（冲销原票）',
  red_unmatched: '红字发票，原票不在系统里',
}

/**
 * 红字发票的配色与标签。
 *
 * 红票是**作废**信号，绝不能复用绿/黄的匹配色：`status-green` 在红票上会被读成
 * 「匹配成功」，而这正是 D5 要杜绝的误读。用 `destructive` 语义令牌（暗色模式
 * 自己会切换），不写死 hex。
 */
export const RED_TONE = {
  label: '红字发票',
  chip: 'border-destructive/30 bg-destructive/10 text-destructive',
  tone: 'text-destructive',
}

/** 冲红重开动作的文案（按钮 / 禁用原因），与后端端点一一对应 */
export const RED_REENACT_COPY = {
  confirm: '冲红并确认重开',
  confirmOnly: '仅冲红',
  blocked: '原票不在系统里，需人工处理',
}

/**
 * 金额格式化：10000.00 → ¥10,000.00
 *
 * 与 `features/payment-intake/constants.ts` 的同名函数逐字同款，但**必须在本域
 * 重新实现**：feature 之间禁止互相 import（见 frontend/CLAUDE.md「禁止 feature
 * 之间互相 import」）。3 行纯函数的重复成本，远低于一条跨域耦合边。
 * 若将来第三个 feature 也需要，再上提到 `lib/formatters`（提权规则：≥2 个
 * feature 共用才提权，且由架构决策统一收敛）。
 */
export function formatAmount(amount: string): string {
  const value = Number(amount)
  if (!Number.isFinite(value)) return `¥${amount}`
  return `¥${value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}
