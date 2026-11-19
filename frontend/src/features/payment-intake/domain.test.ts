import { describe, expect, it } from 'vitest'

import {
  amountText,
  candidateReason,
  contractHint,
  filterContracts,
  hasUsableSuggestion,
  hintText,
  intakeHeadline,
  intakeShape,
} from './domain'
import type { Intake, IntakeCandidate, SelectableContract } from './types'

function candidate(overrides: Partial<IntakeCandidate> = {}): IntakeCandidate {
  return {
    contract_id: 1,
    contract_name: '测试项目',
    kind: 'exact',
    score: 0.9,
    reasons: ['付款人命中委托人「张三」'],
    outstanding_amount: '10000.00',
    fee_mode: 'FIXED',
    caveat: '',
    ...overrides,
  }
}

function intake(overrides: Partial<Intake> = {}): Intake {
  return {
    id: 1,
    amount: '2400.00',
    received_at: '2026-11-04',
    payer_name: '张三',
    on_behalf_of: '',
    display_payer: '张三',
    status: 'pending',
    status_label: '待确认',
    bank_remark: '',
    suggested_contract_id: 1,
    suggested_contract_name: '测试项目',
    confirmed_contract_id: null,
    confirmed_contract_name: null,
    payment_id: null,
    decision_note: '',
    candidates: [candidate()],
    excluded_hints: [],
    inbox_message_id: 10,
    subject: '',
    sender: '',
    ...overrides,
  }
}

describe('intakeShape', () => {
  it('无候选 → unmatched', () => {
    expect(intakeShape(intake({ candidates: [] }))).toBe('unmatched')
  })

  it('实名命中 → matched', () => {
    expect(intakeShape(intake())).toBe('matched')
  })

  it('仅金额吻合 → amountOnly', () => {
    expect(intakeShape(intake({ candidates: [candidate({ kind: 'amount_only' })] }))).toBe('amountOnly')
  })
})

describe('hasUsableSuggestion', () => {
  it('有建议且有实名命中 → true', () => {
    expect(hasUsableSuggestion(intake())).toBe(true)
  })

  it('没有建议 → false', () => {
    expect(hasUsableSuggestion(intake({ suggested_contract_id: null }))).toBe(false)
  })

  it('建议存在但候选只是 amount_only → false（不暗示用户直接点）', () => {
    const row = intake({
      suggested_contract_id: 5,
      candidates: [candidate({ kind: 'amount_only', contract_id: 5 })],
    })
    expect(hasUsableSuggestion(row)).toBe(false)
  })
})

describe('intakeHeadline', () => {
  it('无候选时提示手动选择', () => {
    expect(intakeHeadline(intake({ candidates: [] }))).toContain('请手动选择')
  })

  it('仅金额吻合时强提醒核对', () => {
    const row = intake({ candidates: [candidate({ kind: 'amount_only' })] })
    expect(intakeHeadline(row)).toContain('核对')
  })

  it('实名命中时给出项目名', () => {
    expect(intakeHeadline(intake())).toContain('测试项目')
  })
})

describe('amountText', () => {
  it('千分位 + 两位小数', () => {
    expect(amountText(intake({ amount: '2400' }))).toBe('¥2,400.00')
    expect(amountText(intake({ amount: '10000.00' }))).toBe('¥10,000.00')
  })

  it('非法值不炸，原样带币种', () => {
    expect(amountText(intake({ amount: 'abc' }))).toBe('¥abc')
  })
})

describe('hintText', () => {
  it('优先用后端的人话说明（含金额对比）', () => {
    expect(
      hintText({
        excluded_by: 'fully_paid',
        note: '费用已收齐（50000.00/50000.00），如需追加收费请先新建合同',
        contract_name: 'x',
      }),
    ).toContain('50000.00/50000.00')
  })

  it('note 与标签相同时退回标签', () => {
    expect(hintText({ excluded_by: 'fully_paid', note: '费用已收齐', contract_name: 'x' })).toBe('费用已收齐')
  })

  it('未知原因兜底原值', () => {
    expect(hintText({ excluded_by: 'weird', note: '', contract_name: 'x' })).toBe('weird')
  })
})

describe('candidateReason', () => {
  it('取第一条理由', () => {
    expect(candidateReason(candidate())).toBe('付款人命中委托人「张三」')
  })

  it('没有理由返回空串', () => {
    expect(candidateReason(candidate({ reasons: [] }))).toBe('')
  })
})

describe('contractHint', () => {
  function contract(overrides: Partial<SelectableContract> = {}): SelectableContract {
    return {
      id: 1,
      name: '项目',
      fee_mode: 'FIXED',
      fixed_amount: '10000',
      paid_total: '3000',
      outstanding_amount: '7000',
      expires_note: '',
      ...overrides,
    }
  }

  it('显示应收余额', () => {
    expect(contractHint(contract())).toContain('应收余额')
  })

  it('到期项目带出到期提示', () => {
    expect(contractHint(contract({ expires_note: '已于 2026-01-01 到期' }))).toContain('到期')
  })

  it('两者都有时用 · 连接', () => {
    expect(contractHint(contract({ expires_note: '已于 2026-01-01 到期' }))).toContain('·')
  })
})

describe('filterContracts', () => {
  const rows: SelectableContract[] = [
    { id: 1, name: '甲公司合同', fee_mode: 'FIXED', fixed_amount: null, paid_total: null, outstanding_amount: null, expires_note: '' },
    { id: 2, name: '乙公司合同', fee_mode: 'FIXED', fixed_amount: null, paid_total: null, outstanding_amount: null, expires_note: '' },
  ]

  it('空关键词返回全部', () => {
    expect(filterContracts(rows, '  ')).toHaveLength(2)
  })

  it('按名称过滤', () => {
    expect(filterContracts(rows, '甲').map((r) => r.id)).toEqual([1])
  })
})

describe('AI 兜底建议（ai_suggested）', () => {
  // 后端 contract_match_ai：规则拿不到任何实名证据时才让 LLM 从候选里挑。
  // 前端必须把它当「需核对」而不是「已确定」，否则用户会以为系统认定了。

  it('AI 候选同样要求核对（不归入 matched）', () => {
    expect(intakeShape(intake({ candidates: [candidate({ kind: 'ai_suggested' })] }))).toBe('amountOnly')
  })

  it('AI 候选不提供「确认建议」按钮', () => {
    const ai = intake({
      candidates: [candidate({ kind: 'ai_suggested', contract_id: 7 })],
      suggested_contract_id: 7,
    })
    expect(hasUsableSuggestion(ai)).toBe(false)
  })

  it('标题明确标注是 AI 推断', () => {
    const ai = intake({ candidates: [candidate({ kind: 'ai_suggested' })] })
    expect(intakeHeadline(ai)).toContain('AI')
  })

  it('仅金额吻合的标题不带 AI 字样（两者不混淆）', () => {
    const amountOnly = intake({ candidates: [candidate({ kind: 'amount_only' })] })
    expect(intakeHeadline(amountOnly)).not.toContain('AI')
  })
})
