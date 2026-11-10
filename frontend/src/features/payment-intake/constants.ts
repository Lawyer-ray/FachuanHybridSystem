import type { CandidateKind } from './types'

/**
 * 判定类别的文案与配色。
 *
 * 三档的可信度差异很大，必须让用户一眼分清"系统很确定"和"只是金额碰巧相等"：
 * - exact：付款人/案号实名命中委托人 —— 可以直接点确认；
 * - partial：实名命中但金额对不上 —— 常见于分期/尾款，通常也对；
 * - amount_only：**只有金额撞上**，无任何身份证据 —— 极易错，必须自己核对。
 */
export interface KindStyle {
  label: string
  /** 主文案颜色（Tailwind 类） */
  tone: string
  /** 底色 + 边框 */
  chip: string
  /** 是否需要在卡片上强提醒 */
  risky: boolean
}

export const KIND_STYLES: Record<CandidateKind, KindStyle> = {
  exact: {
    label: '高度匹配',
    tone: 'text-status-green',
    chip: 'border-status-green/30 bg-status-green-bg text-status-green',
    risky: false,
  },
  partial: {
    label: '当事人匹配',
    tone: 'text-status-yellow',
    chip: 'border-status-yellow/30 bg-status-yellow-bg text-status-yellow',
    risky: false,
  },
  amount_only: {
    label: '仅金额吻合',
    tone: 'text-muted-foreground',
    chip: 'border-border bg-secondary text-muted-foreground',
    risky: true,
  },
}

/** 排除原因的人话标签（与后端 EXCLUDED_LABELS 对应，前端只用于紧凑展示） */
export const EXCLUDED_LABELS: Record<string, string> = {
  fully_paid: '费用已收齐',
  archived: '已归档',
  unsigned: '未签约',
  case_closed: '案件已结案',
}

/** 金额格式化：10000.00 → ¥10,000.00 */
export function formatAmount(amount: string): string {
  const value = Number(amount)
  if (!Number.isFinite(value)) return `¥${amount}`
  return `¥${value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}
