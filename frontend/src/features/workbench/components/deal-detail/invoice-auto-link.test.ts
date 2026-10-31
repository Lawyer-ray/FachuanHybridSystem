import { describe, expect, it } from 'vitest'

import {
  amountOf,
  autoAttachTarget,
  groupsForReview,
  splitByAmountMatch,
  type PoolInvoice,
} from './invoice-auto-link'

const inv = (id: number, paymentId: number | null, total: string | null = '9000.00'): PoolInvoice => ({
  id,
  payment_id: paymentId,
  total_amount: total,
})

describe('amountOf', () => {
  it('去掉 ¥ / 千分位 / 空白后取数', () => {
    expect(amountOf('¥9,000.00')).toBe(9000)
    expect(amountOf(' 9000 ')).toBe(9000)
    expect(amountOf('￥3000.50')).toBe(3000.5)
    expect(amountOf('')).toBeNull()
    expect(amountOf(null)).toBeNull()
    expect(amountOf('金额未识别')).toBeNull()
  })
})

describe('autoAttachTarget', () => {
  it('合同下仅一笔收款：把待归属的票自动挂给它', () => {
    expect(autoAttachTarget([{ id: 7, amount: '9000.00' }], [inv(1, null)])).toBe(7)
  })

  it('没有待归属的票：不动作', () => {
    expect(autoAttachTarget([{ id: 7, amount: '9000.00' }], [inv(1, 7)])).toBeNull()
    expect(autoAttachTarget([{ id: 7, amount: '9000.00' }], [])).toBeNull()
  })

  it('多笔收款：交还给人判断（不猜哪张票算哪笔）', () => {
    const payments = [
      { id: 7, amount: '9000.00' },
      { id: 8, amount: '3000.00' },
    ]
    expect(autoAttachTarget(payments, [inv(1, null)])).toBeNull()
  })

  it('一笔收款都没有（理论上不会发生）：不动作', () => {
    expect(autoAttachTarget([], [inv(1, null)])).toBeNull()
  })
})

describe('splitByAmountMatch', () => {
  it('金额吻合与不吻合分开，供提示文案区分', () => {
    const out = splitByAmountMatch([inv(1, 7, '9000.00'), inv(2, 7, '3000.00')], 9000)
    expect(out.attached.map((i) => i.id)).toEqual([1])
    expect(out.amountMismatch.map((i) => i.id)).toEqual([2])
  })

  it('金额未识别（null）归入「不吻合」，不假装对上', () => {
    const out = splitByAmountMatch([inv(1, 7, null)], 9000)
    expect(out.amountMismatch.map((i) => i.id)).toEqual([1])
  })

  it('不知道收款金额时不做拆分（全部按已关联）', () => {
    const out = splitByAmountMatch([inv(1, 7, '9000.00')], null)
    expect(out.attached).toHaveLength(1)
    expect(out.amountMismatch).toHaveLength(0)
  })
})

describe('groupsForReview', () => {
  const payments = [
    { id: 7, amount: '3000.00' },
    { id: 8, amount: '9000.00' },
  ]

  it('按收款分组，金额大的在前，未归属的单独一组放最后', () => {
    const groups = groupsForReview([inv(1, 7), inv(2, 8), inv(3, null)], payments)
    expect(groups.map((g) => g.paymentId)).toEqual([8, 7, null])
    expect(groups[2]?.invoices.map((i) => i.id)).toEqual([3])
  })

  it('同一笔收款的票聚在一组（挂错时可整组核对、解绑重挂）', () => {
    const groups = groupsForReview([inv(1, 8), inv(2, 8)], payments)
    expect(groups).toHaveLength(1)
    expect(groups[0]?.invoices.map((i) => i.id)).toEqual([1, 2])
  })

  it('没有未归属的票就不出空组', () => {
    const groups = groupsForReview([inv(1, 8)], payments)
    expect(groups.map((g) => g.paymentId)).toEqual([8])
  })

  it('收款已不在列表里（被删）的票仍能分组显示，不丢行', () => {
    const groups = groupsForReview([inv(1, 999)], payments)
    expect(groups).toHaveLength(1)
    expect(groups[0]?.paymentId).toBe(999)
  })
})
