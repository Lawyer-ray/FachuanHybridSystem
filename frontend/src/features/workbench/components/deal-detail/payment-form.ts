/**
 * 记收款弹窗的纯逻辑：短信草稿 → 表单初值、表单 → 提交载荷、金额校验。
 *
 * 与组件分离的原因：金额/日期换算最容易出错（也是财务风险点），抽成纯函数
 * 才能在 node 环境里单测，不必渲染整个对话框。
 */

import type { PaymentParseDraft } from '../../api'

/** 记收款表单的本地状态（金额/日期都用 input 的原生字符串形态） */
export interface PaymentForm {
  amount: string
  receivedAt: string
  invoicedAmount: string
  note: string
  /** 短信里认出的付款人。ContractPayment 没有付款人字段，这里只用于展示与提示 */
  payer: string
}

export const EMPTY_FORM: PaymentForm = {
  amount: '',
  receivedAt: '',
  invoicedAmount: '',
  note: '',
  payer: '',
}

/** 今天（yyyy-mm-dd，本地时区；不能用 toISOString——那是 UTC，凌晨会差一天） */
export function todayISO(now: Date = new Date()): string {
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const d = String(now.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/**
 * 短信草稿 → 表单初值。
 *
 * 备注拼上付款人：`ContractPayment.note` 是唯一能存自由文本的字段，
 * 而「谁付的」恰恰是日后对账时最想看到的信息。
 */
export function formFromDraft(d: PaymentParseDraft): PaymentForm {
  const parts: string[] = []
  if (d.payer) parts.push(`付款人：${d.payer}`)
  if (d.note) parts.push(d.note)
  return {
    amount: d.amount ?? '',
    // 短信没写日期就不猜：留空让 input 显示 placeholder，而不是偷偷填今天
    receivedAt: d.received_at ?? '',
    invoicedAmount: '',
    note: parts.join('；'),
    payer: d.payer,
  }
}

/** 金额串 → number（容忍千分位、全角逗号、¥ 前缀、空白） */
export function parseAmount(raw: string): number | null {
  const cleaned = raw.replace(/[¥￥,\s，]/g, '')
  if (!cleaned) return null
  const n = Number(cleaned)
  return Number.isFinite(n) ? n : null
}

/** 提交前校验。返回 null = 可提交，否则是给人看的中文原因 */
export function validateForm(f: PaymentForm): string | null {
  const amount = parseAmount(f.amount)
  if (amount == null) return '请填写收款金额'
  if (amount <= 0) return '收款金额需大于 0'
  if (!f.receivedAt) return '请选择收款日期'
  if (!/^\d{4}-\d{2}-\d{2}$/.test(f.receivedAt)) return '收款日期格式不正确'

  const invoiced = f.invoicedAmount.trim() ? parseAmount(f.invoicedAmount) : 0
  if (invoiced == null || invoiced < 0) return '开票金额不能为负'
  if (invoiced > amount) return '开票金额不能大于收款金额'
  return null
}

/** 表单 → 后端 `POST /finance/payments` 的载荷（payload 形状由 ContractPaymentIn 定） */
export function toCreatePayload(contractId: number, f: PaymentForm): Record<string, unknown> {
  const invoiced = f.invoicedAmount.trim() ? (parseAmount(f.invoicedAmount) ?? 0) : 0
  return {
    contract_id: contractId,
    amount: parseAmount(f.amount) ?? 0,
    received_at: f.receivedAt,
    invoiced_amount: invoiced,
    note: f.note.trim(),
    // 后端强制二次确认（`关键操作需二次确认`）：记收款是财务写入，前端弹窗
    // 本身就是确认动作，这里直接置 true，不要为了绕过校验另建一条路径。
    confirm: true,
  }
}

/** 剩余可收（合同固定金额 - 已收），用于在弹窗里提示「这笔会超过合同额」 */
export function remainingLabel(fixedAmount: number | null, received: number): string | null {
  if (fixedAmount == null || !Number.isFinite(fixedAmount)) return null
  return (fixedAmount - received).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
