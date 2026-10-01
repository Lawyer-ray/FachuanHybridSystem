import { describe, expect, it } from 'vitest'
import {
  buildDealCases,
  buildDeals,
  daysFromToday,
  fmtMoney,
  groupDeals,
  lawyerCopyText,
  partyCopyText,
  relDue,
} from './domain'
import type { CaseListItem, ContractListItem, LawyerListItem } from './types'

const TODAY = new Date(2026, 9, 1) // 2026-10-01，固定基准

function makeContract(partial: Partial<ContractListItem> = {}): ContractListItem {
  return {
    id: 1,
    name: '张三',
    case_type: 'civil',
    case_type_label: '民商事',
    status: 'active',
    status_label: '在办',
    specified_date: null,
    start_date: '2026-01-10',
    end_date: '2026-10-01',
    is_filed: false,
    filing_number: null,
    fee_mode: '固定收费',
    fixed_amount: 50000,
    risk_rate: null,
    custom_terms: null,
    representation_stages: [],
    law_firm_oa_url: null,
    law_firm_oa_case_number: 'OA-001',
    total_received: 20000,
    total_invoiced: null,
    unpaid_amount: 30000,
    contract_parties: [
      { id: 1, role_label: '委托人', client_detail: { id: 1, name: '张三', is_our_client: true, phone: '13800000000', address: null, client_type_label: '自然人', id_number: '4401***', legal_representative: null } },
      { id: 2, role_label: '对方当事人', client_detail: { id: 2, name: '李四公司', is_our_client: false, phone: null, address: '广州市', client_type_label: '法人', id_number: null, legal_representative: '王五' } },
    ],
    assignments: [{ id: 1, lawyer_id: 9, lawyer_name: null, is_primary: true }],
    primary_lawyer: { id: 9, real_name: '赵律师', phone: '13900000000', law_firm_name: '某律所' },
    reminders: [{ id: 1, content: '开庭', due_at: '2026-10-01T09:00:00Z', reminder_type_label: '开庭' }],
    payments: [],
    client_payment_records: [],
    supplementary_agreements: [],
    case_count: 1,
    ...partial,
  }
}

function makeCase(partial: Partial<CaseListItem> = {}): CaseListItem {
  return {
    id: 11,
    contract_id: 1,
    name: '张三与李四买卖合同纠纷',
    status: '在办',
    current_stage: '一审',
    case_numbers: [{ id: 1, number: '(2026)粤01民初1号' }],
    supervising_authorities: [],
    cause_of_action: '买卖合同纠纷',
    target_amount: null,
    preservation_amount: null,
    start_date: '2026-03-01',
    effective_date: null,
    parties: [],
    logs: [],
    contacts: [],
    ...partial,
  }
}

describe('fmtMoney', () => {
  it('空值与 0 返回 null', () => {
    expect(fmtMoney(null)).toBeNull()
    expect(fmtMoney(undefined)).toBeNull()
    expect(fmtMoney(0)).toBeNull()
  })
  it('格式化为千分位', () => {
    expect(fmtMoney(50000)).toBe('¥50,000')
    expect(fmtMoney('1200000')).toBe('¥1,200,000')
  })
})

describe('daysFromToday / relDue', () => {
  it('空串返回 null', () => {
    expect(daysFromToday('', TODAY)).toBeNull()
    expect(daysFromToday(null, TODAY)).toBeNull()
  })
  it('今日 / 过期 / 两个月内 / 更远', () => {
    expect(daysFromToday('2026-10-01', TODAY)).toBe(0)
    expect(daysFromToday('2026-09-30', TODAY)).toBe(-1)
    expect(relDue(0)).toBe('今日到期')
    expect(relDue(-2)).toBe('已到期 2 天')
    expect(relDue(30)).toBe('剩 30 天')
    expect(relDue(120)).toBe('剩 4 个月')
    expect(relDue(null)).toBe('')
  })
})

describe('buildDeals', () => {
  const lawyers: LawyerListItem[] = [
    { id: 9, username: 'zhao', real_name: '赵律师', phone: '13911111111', license_no: ' 14401xxx ', law_firm_detail: { id: 1, name: '某律所' } },
  ]
  const deals = buildDeals([makeContract()], lawyers, TODAY)

  it('合并合同/律师：副行我方对方、caseCount、证号去除空白', () => {
    expect(deals).toHaveLength(1)
    const d = deals[0]!
    expect(d.parties).toEqual({ client: '张三', other: '李四公司' })
    expect(d.caseCount).toBe(1)
    expect(d.team[0]!.license).toBe('14401xxx')
    expect(d.lit).toBe(true)
  })
  it('buildDealCases：程序阶段取 current_stage、已结案判定', () => {
    const dc = buildDealCases([makeCase()], TODAY)
    expect(dc).toHaveLength(1)
    expect(dc[0]!.proc).toBe('一审')
    expect(dc[0]!.done).toBe(false)
  })
  it('提醒映射日期截取', () => {
    expect(deals[0]!.work[0]?.dueFull).toBe('2026-10-01')
  })
  it('case_count 透传（按需加载的计数口径）', () => {
    const d2 = buildDeals([makeContract({ id: 2, case_count: 3 })], lawyers, TODAY)
    expect(d2[0]!.caseCount).toBe(3)
  })
})

describe('groupDeals', () => {
  it('未选类目时诉讼组在前非诉在后', () => {
    const deals = buildDeals(
      [
        makeContract({ id: 1, case_type: 'advisor', case_type_label: '常法顾问' }),
        makeContract({ id: 2 }),
        makeContract({ id: 3, case_type: 'advisor', case_type_label: '常法顾问' }),
      ],
      [],
      TODAY,
    )
    const groups = groupDeals(deals, false)
    expect(groups.map((g) => g.type)).toEqual(['民商事', '常法顾问'])
    expect(groups[0]!.lit).toBe(true)
  })
  it('选了具体类目时不再重排（数量序）', () => {
    const deals = buildDeals(
      [makeContract({ id: 1, case_type: 'advisor', case_type_label: '常法顾问' }), makeContract({ id: 2 })],
      [],
      TODAY,
    )
    expect(groupDeals(deals, true).map((g) => g.type)).toEqual(['常法顾问', '民商事'])
  })
})

describe('复制文本', () => {
  it('当事人：空字段跳过，角色与类型拼接', () => {
    expect(partyCopyText({ name: '张三', role: '委托人', type: '自然人', idno: '4401', legalRep: '', phone: '138', address: '', ours: true })).toBe(
      '张三（委托人 · 自然人）\n证件号：4401\n电话：138',
    )
  })
  it('律师：主办标注、主办回落合同律所', () => {
    const d = buildDeals([makeContract()], [], TODAY)[0]!
    expect(lawyerCopyText({ name: '赵律师', primary: true, phone: '', license: '144', firm: '' }, d)).toBe(
      '赵律师（主办）\n电话：13900000000\n执业证号：144\n律所：某律所',
    )
  })
})
