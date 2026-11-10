import { describe, expect, it } from 'vitest'

import { formatAmount } from './constants'
import { amountText, canConfirm, hasUsableSuggestion, invoiceHeadline, invoiceSubtitle } from './domain'
import type { InvoiceCandidate, InvoiceIntake } from './types'

function candidate(overrides: Partial<InvoiceCandidate> = {}): InvoiceCandidate {
  return {
    contract_id: 160,
    contract_name: '张某与某公司合同纠纷',
    kind: 'project_code',
    score: 1,
    reasons: ['备注栏项目号 2025GZM0001 命中'], // privacy-allow 虚构样例，非真实项目号
    caveat: '',
    ...overrides,
  }
}

function intake(overrides: Partial<InvoiceIntake> = {}): InvoiceIntake {
  return {
    id: 1,
    invoice_number: '26442000012915552076',
    invoice_date: '2026-11-04',
    total_amount: '2400.00',
    buyer_name: '张三',
    project_code: '2025GZM0001', // privacy-allow 虚构样例，非真实项目号
    remark: '2025GZM0001-张某与某公司合同纠纷', // privacy-allow 虚构样例，非真实项目号
    status: 'pending',
    status_label: '待确认',
    suggested_contract_id: 160,
    suggested_contract_name: '张某与某公司合同纠纷',
    suggested_payment_id: null,
    payment_pick_confidence: 'no_payment',
    payment_pick_note: '',
    payment_options: [],
    confirmed_contract_id: null,
    confirmed_contract_name: null,
    confirmed_payment_id: null,
    invoice_id: null,
    candidates: [candidate()],
    excluded_hints: [],
    inbox_message_id: 10,
    subject: '',
    sender: '',
    ...overrides,
  }
}

describe('invoiceHeadline', () => {
  it('有建议时给出信号标签 + 项目名', () => {
    expect(invoiceHeadline(intake())).toBe('✓ 确定性匹配：张某与某公司合同纠纷')
  })

  it('按最高信号等级取标签：同时有项目号与当事人匹配时用项目号', () => {
    const row = intake({
      candidates: [
        candidate({ contract_id: 9, kind: 'party_name', contract_name: '别的项目' }),
        candidate({ kind: 'case_text' }),
        candidate({ kind: 'project_code' }),
      ],
    })
    expect(invoiceHeadline(row)).toBe('✓ 确定性匹配：张某与某公司合同纠纷')
  })

  it('只有案由匹配时用案由标签', () => {
    const row = intake({ candidates: [candidate({ kind: 'case_text' })] })
    expect(invoiceHeadline(row)).toContain('案由匹配')
  })

  it('只有当事人匹配时用当事人标签', () => {
    const row = intake({ candidates: [candidate({ kind: 'party_name' })] })
    expect(invoiceHeadline(row)).toContain('当事人匹配')
  })

  it('有建议但无候选时退回「系统建议」，不空标签', () => {
    const row = intake({ candidates: [] })
    expect(invoiceHeadline(row)).toBe('✓ 系统建议：张某与某公司合同纠纷')
  })

  it('无建议时明说要人工选择', () => {
    const row = intake({ suggested_contract_id: null, suggested_contract_name: null, candidates: [] })
    expect(invoiceHeadline(row)).toBe('无可匹配的在办项目，需人工选择')
  })
})

describe('hasUsableSuggestion', () => {
  it('有建议 → true', () => {
    expect(hasUsableSuggestion(intake())).toBe(true)
  })

  it('无建议 → false', () => {
    expect(hasUsableSuggestion(intake({ suggested_contract_id: null }))).toBe(false)
  })

  it('只认 id，不看合同名是否为空', () => {
    expect(hasUsableSuggestion(intake({ suggested_contract_name: null }))).toBe(true)
  })
})

describe('canConfirm', () => {
  it('待确认 + 有建议 → true', () => {
    expect(canConfirm(intake())).toBe(true)
  })

  it('无建议 → false', () => {
    expect(canConfirm(intake({ suggested_contract_id: null }))).toBe(false)
  })

  it('已绑定的不再可确认 → false', () => {
    expect(canConfirm(intake({ status: 'confirmed' }))).toBe(false)
  })
})

describe('invoiceSubtitle', () => {
  it('购买方 · 去掉项目号后的案由片段', () => {
    expect(invoiceSubtitle(intake())).toBe('张三 · 张某与某公司合同纠纷')
  })

  it('案由超 30 字截断加省略号', () => {
    const remark = `2025GZM0001-${'长'.repeat(40)}` // privacy-allow 虚构样例，非真实项目号
    const text = invoiceSubtitle(intake({ remark }))
    expect(text).toContain('…')
    expect(text.length).toBeLessThan(40)
  })

  it('无案由时只剩购买方，不留悬空分隔符', () => {
    expect(invoiceSubtitle(intake({ remark: '', project_code: '' }))).toBe('张三')
  })

  it('无购买方时只剩案由', () => {
    expect(invoiceSubtitle(intake({ buyer_name: '' }))).toBe('张某与某公司合同纠纷')
  })
})

describe('amountText', () => {
  it('金额加币种与千分位', () => {
    expect(amountText(intake())).toBe('¥2,400.00')
  })

  it('识别失败（null）给占位而不是孤零零的 ¥', () => {
    expect(amountText(intake({ total_amount: null }))).toBe('金额未识别')
  })

  it('空串同样给占位', () => {
    expect(amountText(intake({ total_amount: '' }))).toBe('金额未识别')
  })
})

describe('formatAmount', () => {
  it('两位小数 + 千分位', () => {
    expect(formatAmount('10000.00')).toBe('¥10,000.00')
    expect(formatAmount('2400')).toBe('¥2,400.00')
    expect(formatAmount('0')).toBe('¥0.00')
  })

  it('小数按四舍五入保留两位', () => {
    expect(formatAmount('12.345')).toBe('¥12.35')
  })

  it('负数为退款票时保留符号', () => {
    expect(formatAmount('-2400')).toBe('¥-2,400.00')
  })

  it('非法值不炸，原样带币种', () => {
    expect(formatAmount('abc')).toBe('¥abc')
  })

  it('空串按 Number("")===0 输出 ¥0.00，不抛错', () => {
    // 记下这个边界：组件层用 amountText 把 null/'' 提前挡掉，formatAmount 自身不做空值判断
    expect(formatAmount('')).toBe('¥0.00')
  })
})
