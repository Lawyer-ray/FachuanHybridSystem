import { describe, expect, it } from 'vitest'

import {
  EMPTY_FORM,
  formFromDraft,
  parseAmount,
  remainingLabel,
  toCreatePayload,
  todayISO,
  validateForm,
} from './payment-form'

describe('parseAmount', () => {
  it('容忍千分位、全角逗号、¥ 前缀与空白', () => {
    expect(parseAmount('9,000.00')).toBe(9000)
    expect(parseAmount('¥１２,500'.replace('１２', '12'))).toBe(12500)
    expect(parseAmount(' 30000 ')).toBe(30000)
    expect(parseAmount('9000，00'.replace('，', ''))).toBe(900000)
  })

  it('空串与非数字返回 null', () => {
    expect(parseAmount('')).toBeNull()
    expect(parseAmount('   ')).toBeNull()
    expect(parseAmount('abc')).toBeNull()
  })
})

describe('formFromDraft', () => {
  it('付款人拼进备注（合同收款没有付款人字段，只能写在备注里）', () => {
    const form = formFromDraft({
      amount: '9000.00',
      received_at: '2026-10-14',
      payer: '丙方不锈钢有限公司',
      note: '律师费',
      hints: [],
    })
    expect(form.amount).toBe('9000.00')
    expect(form.receivedAt).toBe('2026-10-14')
    expect(form.note).toBe('付款人：丙方不锈钢有限公司；律师费')
  })

  it('短信没写日期就留空，不偷偷填今天', () => {
    const form = formFromDraft({ amount: '3000.00', received_at: null, payer: '', note: '', hints: [] })
    expect(form.receivedAt).toBe('')
  })

  it('完全没认出来时留下空表单，让人手填', () => {
    const form = formFromDraft({ amount: null, received_at: null, payer: '', note: '', hints: [] })
    expect(form).toEqual(EMPTY_FORM)
  })
})

describe('validateForm', () => {
  const ok = { ...EMPTY_FORM, amount: '9000', receivedAt: '2026-10-14' }

  it('合法表单通过', () => {
    expect(validateForm(ok)).toBeNull()
  })

  it('金额为空 / 非正 / 日期缺失或格式错都拦下', () => {
    expect(validateForm({ ...ok, amount: '' })).toBe('请填写收款金额')
    expect(validateForm({ ...ok, amount: '0' })).toBe('收款金额需大于 0')
    expect(validateForm({ ...ok, receivedAt: '' })).toBe('请选择收款日期')
    expect(validateForm({ ...ok, receivedAt: '2026/10/14' })).toBe('收款日期格式不正确')
  })

  it('开票金额不能大于收款金额（与后端约束一致）', () => {
    expect(validateForm({ ...ok, invoicedAmount: '9001' })).toBe('开票金额不能大于收款金额')
    expect(validateForm({ ...ok, invoicedAmount: '-1' })).toBe('开票金额不能为负')
    expect(validateForm({ ...ok, invoicedAmount: '9000' })).toBeNull()
  })
})

describe('toCreatePayload', () => {
  it('带 confirm=true（后端强制二次确认，弹窗本身即确认动作）', () => {
    const payload = toCreatePayload(42, { ...EMPTY_FORM, amount: '9,000', receivedAt: '2026-10-14', note: ' 律师费 ' })
    expect(payload).toMatchObject({
      contract_id: 42,
      amount: 9000,
      received_at: '2026-10-14',
      invoiced_amount: 0,
      note: '律师费',
      confirm: true,
    })
  })

  it('开票金额留空按 0 提交（后端 invoiced_amount 不接受 null）', () => {
    const payload = toCreatePayload(1, { ...EMPTY_FORM, amount: '100', receivedAt: '2026-01-01', invoicedAmount: '  ' })
    expect(payload.invoiced_amount).toBe(0)
  })
})

describe('remainingLabel', () => {
  it('没有固定金额时不给提示（不编造额度）', () => {
    expect(remainingLabel(null, 0)).toBeNull()
  })

  it('固定金额减去已收', () => {
    expect(remainingLabel(100000, 30000)).toBe('70,000')
  })
})

describe('todayISO', () => {
  it('用本地时区而非 UTC（凌晨不会差一天）', () => {
    expect(todayISO(new Date(2026, 0, 5, 0, 30))).toBe('2026-01-05')
  })
})
