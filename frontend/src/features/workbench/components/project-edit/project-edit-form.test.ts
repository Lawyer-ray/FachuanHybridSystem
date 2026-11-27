import { describe, expect, it } from 'vitest'

import type { ContractListItem } from '../../types'
import { formFromContract, toUpdatePayload, validateForm } from './project-edit-form'

/**
 * 差量与校验是这一页最容易错的两处：
 * - 写接口是 `exclude_unset`：多发一个键就可能把别人刚改的值打回去，
 *   发 `null` 更是直接把字段清空（有些列还不允许 null → 500）；
 * - 后端对日期/比例基本不校验（写错直接 500），前端必须先拦住。
 */
function contract(over: Partial<ContractListItem> = {}): ContractListItem {
  return {
    id: 7,
    name: '某银行与某公司金融借款合同纠纷诉讼委托合同',
    case_type: 'civil',
    status: 'active',
    specified_date: '2026-03-11',
    start_date: '2026-03-11',
    end_date: null,
    is_filed: false,
    fee_mode: '固定收费',
    fixed_amount: '50000.00',
    risk_rate: null,
    custom_terms: '',
    representation_stages: ['一审', '执行'],
    ...over,
  } as unknown as ContractListItem
}

describe('formFromContract（标签 → 代码回填）', () => {
  it('fee_mode 中文标签回填成代码', () => {
    expect(formFromContract(contract({ fee_mode: '半风险收费' })).feeMode).toBe('SEMI_RISK')
  })

  it('representation_stages 中文标签回填成代码', () => {
    expect(formFromContract(contract()).stages).toEqual(['first_trial', 'enforcement'])
  })

  it('金额按原始字符串回填（后端下发的是 "50000.00"）', () => {
    expect(formFromContract(contract()).fixedAmount).toBe('50000.00')
  })
})

describe('toUpdatePayload（只发脏字段）', () => {
  it('没有任何改动 → 空 payload，也不会带财务确认', () => {
    const c = contract()
    const { payload, confirmFinance } = toUpdatePayload(formFromContract(c), c)
    expect(payload).toEqual({})
    expect(confirmFinance).toBe(false)
  })

  it('只改名字 → 只发 name，不带 confirm_finance', () => {
    const c = contract()
    const form = { ...formFromContract(c), name: '新名字' }
    const { payload, confirmFinance } = toUpdatePayload(form, c)
    expect(payload).toEqual({ name: '新名字' })
    expect(confirmFinance).toBe(false)
  })

  it('清空结束日期 → 发 null（省略该键等于「不修改」）', () => {
    const c = contract({ end_date: '2026-12-31' })
    const form = { ...formFromContract(c), to: '' }
    expect(toUpdatePayload(form, c).payload).toEqual({ end_date: null })
  })

  it('金额按数值比较：50000 与 50000.00 视为未改（不许发一次假财务变更）', () => {
    const c = contract({ fixed_amount: '50000.00' })
    const form = { ...formFromContract(c), fixedAmount: '50000' }
    expect(toUpdatePayload(form, c).payload).toEqual({})
  })

  it('改收费 → 带 confirmFinance（后端没有它会直接 400）', () => {
    const c = contract()
    const form = { ...formFromContract(c), fixedAmount: '60000' }
    const out = toUpdatePayload(form, c)
    expect(out.payload).toEqual({ fixed_amount: 60000 })
    expect(out.confirmFinance).toBe(true)
  })

  it('改代理阶段 → 发代码数组（不是标签）', () => {
    const c = contract()
    const form = { ...formFromContract(c), stages: ['first_trial'] }
    expect(toUpdatePayload(form, c).payload).toEqual({ representation_stages: ['first_trial'] })
  })
})

describe('validateForm（后端不拦的，前端要拦）', () => {
  it('名称为空 / 超过 100 字都要报', () => {
    expect(validateForm({ ...formFromContract(contract()), name: '  ' }).name).toBeTruthy()
    expect(validateForm({ ...formFromContract(contract()), name: 'x'.repeat(101) }).name).toBeTruthy()
  })

  it('指定日期必填（后端该列 not null，传 null 是 500）', () => {
    expect(validateForm({ ...formFromContract(contract()), specified: '' }).specified).toBeTruthy()
  })

  it('日期格式必须是 YYYY-MM-DD（后端收到 2026/01/02 直接 500）', () => {
    expect(validateForm({ ...formFromContract(contract()), from: '2026/01/02' }).from).toBeTruthy()
  })

  it('结束早于开始要报', () => {
    const f = { ...formFromContract(contract()), from: '2026-05-01', to: '2026-04-01' }
    expect(validateForm(f).to).toBeTruthy()
  })

  it('收费模式与金额/比例的组合约束', () => {
    const base = formFromContract(contract())
    expect(validateForm({ ...base, fixedAmount: '' }).fee).toContain('固定收费')
    expect(validateForm({ ...base, feeMode: 'SEMI_RISK', riskRate: '' }).fee).toContain('半风险')
    expect(validateForm({ ...base, feeMode: 'FULL_RISK', riskRate: '' }).fee).toContain('全风险')
    expect(validateForm({ ...base, feeMode: 'CUSTOM', customTerms: '' }).fee).toContain('自定义')
  })

  it('风险比例超 100 要报（后端会撞 DB 约束变成 500）', () => {
    const f = { ...formFromContract(contract()), feeMode: 'FULL_RISK', riskRate: '150' }
    expect(validateForm(f).riskRate).toBeTruthy()
  })

  it('案型改成非诉后仍勾着诉讼阶段 → 报错并点名', () => {
    const f = { ...formFromContract(contract()), caseType: 'advisor', stages: ['first_trial'] }
    expect(validateForm(f).stages).toContain('first_trial')
  })
})
