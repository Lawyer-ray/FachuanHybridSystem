/**
 * 数字/金额格式化工具
 */

/**
 * 格式化金额（带千分位分隔符，保留 2 位小数）
 * @example formatCurrency(12345.6) → "12,345.60"
 */
export function formatCurrency(amount: number): string {
  return amount.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

/**
 * 格式化金额（带 ¥ 前缀，保留 2 位小数）
 * @example formatAmount(12345.6) → "¥ 12,345.60"
 */
export function formatAmount(amount: number | null | undefined): string {
  if (amount == null) return '—'
  return `¥ ${amount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`
}

/**
 * 格式化整数金额（带 ¥ 前缀，无小数）
 * @example formatAmountInt(12345) → "¥12,345"
 */
export function formatAmountInt(amount: number | null | undefined): string {
  if (amount == null) return '—'
  return `¥${amount.toLocaleString()}`
}
