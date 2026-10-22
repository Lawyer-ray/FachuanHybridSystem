import { describe, expect, it } from 'vitest'
import {
  aggregateStages,
  buildDealCases,
  buildDeals,
  daysFromToday,
  dealFacts,
  dealPayRows,
  fmtCNDate,
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
    specified_date: '2026-09-20',
    start_date: '2026-01-10',
    end_date: '2026-10-01',
    is_filed: false,
    filing_number: null,
    fee_mode: '固定收费',
    fixed_amount: '50000',
    risk_rate: null,
    custom_terms: null,
    representation_stages: [],
    law_firm_oa_url: null,
    law_firm_oa_case_number: 'OA-001',
    has_matched_templates: false,
    can_archive: false,
    total_received: 20000,
    total_invoiced: 0,
    unpaid_amount: 30000,
    contract_parties: [
      { id: 1, contract: 1, client: 1, role: 'PRINCIPAL', role_label: '委托人', client_detail: { id: 1, name: '张三', is_our_client: true, phone: '13800000000', address: null, client_type: 'natural', client_type_label: '自然人', id_number: '4401***', legal_representative: null, legal_representative_id_number: null, identity_docs: [] } },
      { id: 2, contract: 1, client: 2, role: 'OPPOSING', role_label: '对方当事人', client_detail: { id: 2, name: '李四公司', is_our_client: false, phone: null, address: '广州市', client_type: 'legal', client_type_label: '法人', id_number: null, legal_representative: '王五', legal_representative_id_number: null, identity_docs: [] } },
    ],
    assignments: [{ id: 1, lawyer_id: 9, lawyer_name: '', is_primary: true, order: 0 }],
    primary_lawyer: { id: 9, username: 'zhao', real_name: '赵律师', phone: '13900000000', law_firm_name: '某律所' },
    reminders: [{ id: 1, reminder_type: 'court', content: '开庭', due_at: '2026-10-01T09:00:00Z', reminder_type_label: '开庭', metadata: {}, created_at: '2026-09-28T08:00:00Z', updated_at: '2026-09-28T08:00:00Z' }],
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
    case_type: 'civil',
    status: '在办',
    current_stage: '一审',
    case_numbers: [{ id: 1, number: '(2026)粤01民初1号', remarks: null, created_at: '2026-08-01T00:00:00Z' }],
    supervising_authorities: [],
    cause_of_action: '买卖合同纠纷',
    target_amount: null,
    preservation_amount: null,
    start_date: '2026-03-01',
    effective_date: null,
    parties: [],
    logs: [],
    contacts: [],
    assignments: [],
    chats: [],
    is_filed: false,
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
  it('脏日期返回 null，不渲染出 NaN / 1899 年', () => {
    // 回归 2026-10 审查 W-P1-2：非 4-2-2 段曾落到 new Date(NaN) → 「剩 NaN 个月」
    expect(daysFromToday('abc-def-ghi', TODAY)).toBeNull()
    expect(daysFromToday('0-0-0', TODAY)).toBeNull()
    expect(daysFromToday('2026-13-01', TODAY)).toBeNull()
    expect(daysFromToday('2026-10-32', TODAY)).toBeNull()
    expect(daysFromToday('not-a-date', TODAY)).toBeNull()
  })
  it('带时间的 ISO 串仍按日期段计算', () => {
    expect(daysFromToday('2026-10-01T09:30:00Z', TODAY)).toBe(0)
    expect(daysFromToday('2026-10-03T23:59', TODAY)).toBe(2)
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

describe('fmtCNDate', () => {
  it('ISO 中划线转年月日，月日不补零', () => {
    expect(fmtCNDate('2026-09-01')).toBe('2026年9月1日')
    expect(fmtCNDate('2026-12-31')).toBe('2026年12月31日')
  })
  it('带时间的 ISO 串只取日期部分', () => {
    expect(fmtCNDate('2026-10-01T09:00:00Z')).toBe('2026年10月1日')
  })
  it('空值返回空串，不像日期的原样返回', () => {
    expect(fmtCNDate('')).toBe('')
    expect(fmtCNDate(null)).toBe('')
    expect(fmtCNDate(undefined)).toBe('')
    expect(fmtCNDate('待定')).toBe('待定')
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

  it('buildDealCases：阶段缺失回落「未立案」，案号取首个 + 全量', () => {
    const dc = buildDealCases(
      [
        makeCase({
          current_stage: '',
          case_numbers: [
            { id: 1, number: 'A号', remarks: null, created_at: '2026-08-01T00:00:00Z' },
            { id: 2, number: 'B号', remarks: null, created_at: '2026-08-02T00:00:00Z' },
          ],
        }),
      ],
      TODAY,
    )
    expect(dc[0]!.proc).toBe('未立案')
    expect(dc[0]!.ref).toBe('A号')
    expect(dc[0]!.numbers).toEqual(['A号', 'B号'])
  })

  it('buildDealCases：日志按时间倒序，字段逐项映射（时间截断/经办人回落/附件数/今日提醒）', () => {
    const dc = buildDealCases(
      [
        makeCase({
          logs: [
            {
              id: 1,
              created_at: '2026-09-01T10:30:00',
              actor_detail: { id: 1, real_name: '赵律师', username: 'zhao' },
              content: '立案',
              attachments: [
                { id: 1, log: 1, original_filename: 'a.pdf', file_path: null, media_url: null, uploaded_at: '2026-09-01T00:00:00Z' },
                { id: 2, log: 1, original_filename: 'b.pdf', file_path: null, media_url: null, uploaded_at: '2026-09-01T00:00:00Z' },
              ],
              reminders: [],
              updated_at: '2026-09-01T10:31:00',
              case: 11,
              actor: 1,
              reminder_time: null,
            },
            {
              id: 2,
              created_at: '2026-10-01T09:00:00',
              actor_detail: { id: 2, real_name: '', username: 'qian' },
              content: '开庭',
              attachments: [],
              reminders: [],
              updated_at: '2026-10-01T09:01:00',
              case: 11,
              actor: 2,
              reminder_time: '2026-10-01T08:00:00Z',
            },
          ],
        }),
      ],
      TODAY,
    )
    const [latest, older] = dc[0]!.logs
    expect(latest!.when).toBe('2026-10-01T09:00') // slice(0, 16)
    expect(latest!.who).toBe('qian') // real_name 空回落 username
    expect(latest!.rem).toBe('2026-10-01 到期提醒')
    expect(latest!.remToday).toBe(true) // 提醒日 = 基准日 2026-10-01
    expect(older!.who).toBe('赵律师')
    expect(older!.attN).toBe(2)
    expect(older!.rem).toBe('')
    expect(older!.remToday).toBe(false)
  })

  it('buildDealCases：主办机关带类型展示、当事人拼「身份：名称」、联系人映射', () => {
    const dc = buildDealCases(
      [
        makeCase({
          supervising_authorities: [{ id: 1, name: '佛山中院', authority_type: 'trial', authority_type_display: '法院', created_at: '2026-01-01T00:00:00Z' }],
          parties: [
            {
              id: 1,
              case: 11,
              client: 1,
              legal_status: '原告',
              client_detail: {
                id: 1,
                name: '张三',
                is_our_client: true,
                phone: null,
                address: null,
                client_type: 'natural',
                client_type_label: '自然人',
                id_number: null,
                legal_representative: null,
                legal_representative_id_number: null,
                identity_docs: [],
              },
            },
          ],
          contacts: [
            { id: 1, name: '王五', role: 'witness', phone: '138', address: null, stage: '', note: '关键证人', authority_name: null, case_id: 11, authority_id: null, created_at: '2026-09-01T00:00:00Z', updated_at: '2026-09-01T00:00:00Z', role_display: '证人', stage_display: '已通知' },
          ],
        }),
      ],
      TODAY,
    )
    expect(dc[0]!.auth).toBe('佛山中院')
    expect(dc[0]!.auths).toEqual(['佛山中院（法院）'])
    expect(dc[0]!.partyRows).toEqual(['原告：张三'])
    expect(dc[0]!.parties).toEqual([{ status: '原告', name: '张三' }])
    expect(dc[0]!.contacts).toEqual([
      { name: '王五', role: '证人', phone: '138', note: '关键证人', stage: '已通知', authority: '', address: '' },
    ])
  })

  it('buildDeals：团队成员名回落 assignment.lawyer_name → 律师表 real_name → 空', () => {
    const lawyers: LawyerListItem[] = [
      { id: 9, username: 'zhao', real_name: '赵律师', phone: '', license_no: '', law_firm_detail: null },
      { id: 10, username: 'sun', real_name: '孙律师', phone: '', license_no: '', law_firm_detail: null },
    ]
    const deals = buildDeals(
      [
        makeContract({
          id: 1,
          assignments: [
            { id: 1, lawyer_id: 9, lawyer_name: '', is_primary: true, order: 0 }, // 回落到律师表
            { id: 2, lawyer_id: 10, lawyer_name: '孙主办', is_primary: false, order: 1 }, // 优先 assignment 名
            { id: 3, lawyer_id: 99, lawyer_name: '', is_primary: false, order: 2 }, // 都没有 → 空
          ],
        }),
      ],
      lawyers,
      TODAY,
    )
    expect(deals[0]!.team.map((t) => t.name)).toEqual(['赵律师', '孙主办', ''])
  })

  it('提醒映射日期转年月日', () => {
    expect(deals[0]!.work[0]?.dueFull).toBe('2026年10月1日')
  })
  it('case_count 透传（按需加载的计数口径）', () => {
    const d2 = buildDeals([makeContract({ id: 2, case_count: 3 })], lawyers, TODAY)
    expect(d2[0]!.caseCount).toBe(3)
  })
})

describe('groupDeals', () => {
  it('按业务形态分两节：争议解决在前非诉在后，节内领域混排保持原序', () => {
    const deals = buildDeals(
      [
        makeContract({ id: 1, case_type: 'advisor', case_type_label: '常法顾问' }),
        makeContract({ id: 2, case_type: 'criminal', case_type_label: '刑事' }),
        makeContract({ id: 3, case_type: 'special', case_type_label: '专项服务' }),
        makeContract({ id: 4 }),
      ],
      [],
      TODAY,
    )
    const groups = groupDeals(deals)
    expect(groups.map((g) => g.title)).toEqual(['争议解决', '非诉'])
    expect(groups[0]!.lit).toBe(true)
    expect(groups[0]!.deals.map((d) => d.id)).toEqual([2, 4])
    expect(groups[1]!.deals.map((d) => d.id)).toEqual([1, 3])
  })
  it('空节不渲染（类目筛选后只剩单形态）', () => {
    const deals = buildDeals([makeContract({ id: 1, case_type: 'advisor', case_type_label: '常法顾问' })], [], TODAY)
    expect(groupDeals(deals).map((g) => g.title)).toEqual(['非诉'])
  })
})

describe('复制文本', () => {
  it('当事人：首行只有名字，空字段跳过', () => {
    expect(partyCopyText({ name: '张三', role: '委托人', idno: '4401', legalRep: '', phone: '138', address: '', ours: true })).toBe(
      '张三\n证件号：4401\n电话：138',
    )
  })
  it('律师：首行只有名字（不带主办标注），主办回落合同电话/律所', () => {
    const d = buildDeals([makeContract()], [], TODAY)[0]!
    expect(lawyerCopyText({ name: '赵律师', primary: true, phone: '', license: '144', firm: '' }, d)).toBe(
      '赵律师\n电话：13900000000\n执业证号：144\n律所：某律所', // privacy-allow 虚构号码
    )
  })
})

// ============ 复制文本 / 合同抽屉数据 / 阶段聚合（覆盖率补测） ============


describe('partyCopyText', () => {
  it('只填名字时只输出名字', () => {
    expect(partyCopyText({ name: '张三' } as never)).toBe('张三')
  })

  it('各字段齐备时按固定顺序逐行输出', () => {
    const text = partyCopyText({
      name: '张三',
      legalRep: '李四',
      idno: '110101199001011234',
      phone: '13800000000',
      address: '北京市朝阳区',
    } as never)
    expect(text.split('\n')).toEqual([
      '张三',
      '法定代表人：李四',
      '证件号：110101199001011234',
      '电话：13800000000',
      '地址：北京市朝阳区',
    ])
  })

  it('空字段被跳过', () => {
    const text = partyCopyText({ name: '张三', legalRep: '', idno: '', phone: '139', address: '' } as never)
    expect(text).toBe('张三\n电话：139')
  })
})

describe('lawyerCopyText', () => {
  it('主办律师未填电话/律所时回落合同上的主电话与律所', () => {
    const text = lawyerCopyText(
      { name: '王律师', primary: true, phone: '', license: '', firm: '' } as never,
      { primaryPhone: '13700000000', lawFirm: '某某所' } as never,
    )
    expect(text).toContain('电话：13700000000')
    expect(text).toContain('律所：某某所')
  })

  it('非主办律师不回落（只输出自己的字段）', () => {
    const text = lawyerCopyText(
      { name: '李律师', primary: false, phone: '', license: '', firm: '' } as never,
      { primaryPhone: '13700000000', lawFirm: '某某所' } as never,
    )
    expect(text).toBe('李律师')
  })

  it('自有字段优先于回落值', () => {
    const text = lawyerCopyText(
      { name: '王律师', primary: true, phone: '13800138000', license: 'A1', firm: '自有所' } as never,
      { primaryPhone: '13700000000', lawFirm: '合同所' } as never,
    )
    expect(text).toContain('电话：13800138000')
    expect(text).toContain('律所：自有所')
    expect(text).not.toContain('13700000000')
  })
})

describe('dealFacts', () => {
  function baseDeal(over: Record<string, unknown> = {}) {
    return {
      fee: '固定收费',
      riskRate: null,
      specified: '',
      from: '2026-09-01',
      to: '',
      daysLeft: null,
      stages: ['一审'],
      isFiled: false,
      statusLabel: '在办',
      filingNo: '',
      no: 'FC-1',
      ...over,
    } as never
  }

  it('空值行被过滤，只保留有值项', () => {
    const rows = dealFacts(baseDeal())
    const keys = rows.map(([k]) => k)
    expect(keys).toContain('收费方式')
    expect(keys).toContain('签订日期')
    expect(keys).not.toContain('风险比例')
    expect(keys).not.toContain('到期日期')
    expect(keys).not.toContain('建档编号')
  })

  it('风险比例非空时带百分号', () => {
    const rows = dealFacts(baseDeal({ riskRate: 15 }))
    expect(rows.find(([k]) => k === '风险比例')?.[1]).toBe('15%')
  })

  it('到期日期追加相对表述', () => {
    const rows = dealFacts(baseDeal({ to: '2026-12-31', daysLeft: 60 }))
    expect(rows.find(([k]) => k === '到期日期')?.[1]).toContain('（剩 60 天）')
  })

  it('已归档时归档状态显示「已归档」而非原状态', () => {
    const rows = dealFacts(baseDeal({ isFiled: true, statusLabel: '在办' }))
    expect(rows.find(([k]) => k === '归档状态')?.[1]).toBe('已归档')
  })
})

describe('dealPayRows', () => {
  it('合并合同收款与客户付款记录，各自带来源标注', () => {
    const rows = dealPayRows({
      payments: [{ received_at: '2026-10-01', amount: 5000, invoice_status_label: '已开票', note: '首付' }],
      payRecords: [{ created_at: '2026-10-02', amount: 3000, note: '' }],
    } as never)

    expect(rows).toHaveLength(2)
    expect(rows[0]!.note).toBe('已开票 · 首付')
    expect(rows[1]!.note).toBe('客户付款记录')
  })

  it('金额为 0 时回落 ¥0', () => {
    const rows = dealPayRows({ payments: [{ received_at: '', amount: 0, invoice_status_label: '', note: '' }], payRecords: [] } as never)
    expect(rows[0]!.money).toBe('¥0')
  })
})

describe('aggregateStages', () => {
  it('同阶段相邻案件合并计数并累计 live', () => {
    const out = aggregateStages([
      { id: 1, proc: '一审', done: false },
      { id: 2, proc: '一审', done: true },
      { id: 3, proc: '二审', done: true },
    ] as never)

    expect(out).toEqual([
      { stage: '一审', n: 2, live: true },
      { stage: '二审', n: 1, live: false },
    ])
  })

  it('按 id 升序处理（输入乱序也稳定）', () => {
    const out = aggregateStages([
      { id: 3, proc: '二审', done: false },
      { id: 1, proc: '一审', done: false },
    ] as never)
    expect(out.map((s) => s.stage)).toEqual(['一审', '二审'])
  })

  it('空输入返回空数组', () => {
    expect(aggregateStages([])).toEqual([])
  })
})
