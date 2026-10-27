import { describe, expect, it } from 'vitest'

import type { ContractReminder, DealCase, ReminderOut, WorkbenchDeal } from '../../../types'
import {
  buildDeadlines,
  contactGroups,
  dueLabel,
  feeStats,
  moneyRows,
  railFacts,
  railParties,
} from './rail-domain'

const TODAY = new Date(2026, 9, 18) // 2026-10-18

function makeCase(over: Partial<DealCase> = {}): DealCase {
  return {
    id: 1,
    name: '案件',
    proc: '一审',
    ref: '',
    numbers: [],
    st: '在办',
    done: false,
    auth: '',
    auths: [],
    cause: '',
    target: null,
    preserv: null,
    from: '',
    partyRows: [],
    parties: [],
    logs: [],
    logReminders: [],
    contacts: [],
    ...over,
  }
}

function makeDeal(over: Partial<WorkbenchDeal> = {}): WorkbenchDeal {
  return {
    id: 7,
    lit: true,
    caseType: 'civil',
    client: '某银行与某公司金融借款合同纠纷诉讼委托合同',
    ctype: '民商事',
    no: '',
    amount: '¥50,000',
    amountNum: 50000,
    fee: '半风险',
    from: '',
    to: '',
    daysLeft: null,
    status: 'active',
    statusLabel: '在办',
    specified: '',
    isFiled: true,
    filingNo: '2025_MS_HT_0031',
    oaUrl: '',
    customTerms: '',
    parties: { client: '某银行', other: '某公司' },
    partiesAll: [
      { name: '某银行', role: '委托人', idno: '', legalRep: '', phone: '', address: '', ours: true },
      { name: '某公司', role: '对方当事人', idno: '', legalRep: '', phone: '', address: '', ours: false },
      { name: '某五金', role: '对方当事人', idno: '', legalRep: '', phone: '', address: '', ours: false },
    ],
    team: [],
    primaryPhone: '',
    caseCount: 2,
    work: [],
    riskRate: 8,
    stages: [],
    primary: '黄崧',
    lawFirm: '',
    totalReceived: '¥50,000',
    totalInvoiced: null,
    unpaid: null,
    payments: [],
    payRecords: [],
    supps: [],
    ...over,
  }
}

function lite(id: number, due: string, over: Partial<ContractReminder> = {}): ContractReminder {
  return {
    id,
    reminder_type: 'other',
    reminder_type_label: '其他',
    content: '提醒 ' + id,
    due_at: due,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  }
}

function full(id: number, due: string, over: Partial<ReminderOut> = {}): ReminderOut {
  return {
    id,
    reminder_type: 'hearing',
    reminder_type_label: '开庭',
    content: '开庭 ' + id,
    due_at: due,
    is_completed: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...over,
  }
}

describe('右栏', () => {
  it('buildDeadlines：三源合流、过期剔除、已完成剔除、今日标红、按到期升序、scope 归属程序', () => {
    const chain = [
      makeCase({ id: 1, proc: '一审', done: true, logReminders: [lite(11, '2026-10-25T00:00:00+08:00', { content: '续封' })] }),
      makeCase({ id: 2, proc: '二审' }),
    ]
    const out = buildDeadlines(
      [lite(1, '2026-10-20T09:30:00+08:00', { content: '合同直挂' }), lite(2, '2026-10-01T00:00:00+08:00', { content: '已过期' })],
      chain,
      [
        full(21, '2026-10-18T09:30:00+08:00', { case: 2, content: '今天开庭' }),
        full(22, '2026-11-01T00:00:00+08:00', { case: 2, is_completed: true }),
        full(23, '2026-12-01T00:00:00+08:00', { case: 99, content: '孤儿案件' }),
      ],
      TODAY,
    )
    expect(out.map((d) => [d.key, d.due, d.daysLeft, d.today, d.scope, d.content])).toEqual([
      ['r21', '2026-10-18', 0, true, '二审', '今天开庭'],
      ['r1', '2026-10-20', 2, false, '委托', '合同直挂'],
      ['r11', '2026-10-25', 7, false, '一审', '续封'],
      ['r23', '2026-12-01', 44, false, '案件', '孤儿案件'],
    ])
  })

  it('buildDeadlines：同一 id 多源出现只保留首个', () => {
    const r = lite(5, '2026-10-20T00:00:00Z')
    const out = buildDeadlines([r], [makeCase({ logReminders: [r] })], [], TODAY)
    expect(out).toHaveLength(1)
    expect(out[0]!.scope).toBe('委托')
  })

  it('dueLabel：同年月-日、跨年全日期', () => {
    expect(dueLabel('2026-10-20', TODAY)).toBe('10-20')
    expect(dueLabel('2028-01-05', TODAY)).toBe('2028-01-05')
  })

  it('contactGroups：按机构分组，缺机构回落案件审理机构再回落程序名', () => {
    const row = (name: string, authority: string) => ({ name, role: '书记员', phone: '', note: '', stage: '', authority, address: '' })
    const groups = contactGroups([
      makeCase({ id: 1, proc: '一审', auth: '南海法院', contacts: [row('陈', '南海法院'), row('李', '')] }),
      makeCase({ id: 2, proc: '二审', auth: '', contacts: [row('梁', '佛山中院'), row('何', '')] }),
    ])
    expect(groups.map((g) => [g.group, g.rows.map((r) => r.name)])).toEqual([
      ['南海法院', ['陈', '李']],
      ['佛山中院', ['梁']],
      ['二审', ['何']],
    ])
  })

  it('moneyRows：标的/保全取链上首个有值案件，费用拼收费方式，空值不出行；已收/未收移交给统计条', () => {
    const rows = moneyRows(makeDeal(), [makeCase({ target: null }), makeCase({ id: 2, target: 3200000, preserv: 1600000 })])
    expect(rows).toEqual([
      ['标的额', '¥3,200,000'],
      ['保全金额', '¥1,600,000'],
      ['律师费', '¥50,000 · 半风险'],
      ['风险比例', '8%'],
    ])
    expect(moneyRows(makeDeal({ amount: null, fee: '', riskRate: null, totalReceived: null }), [])).toEqual([])
    // 没填金额只有收费方式：标签改「收费方式」，不把方式冒充成律师费数值
    expect(moneyRows(makeDeal({ amount: null, fee: '固定收费', riskRate: null, totalReceived: null }), [])).toEqual([
      ['收费方式', '固定收费'],
    ])
  })

  it('feeStats：已收/已开票为 0 也显式给 ¥0（0 与没显示对财务含义不同）；未收依赖合同额', () => {
    expect(feeStats(makeDeal())).toEqual({ received: '¥50,000', invoiced: '¥0', unpaid: null })
    expect(feeStats(makeDeal({ unpaid: '¥50,000' }))).toEqual({
      received: '¥50,000',
      invoiced: '¥0',
      unpaid: '¥50,000',
    })
    // 无任何收款：已收也是显式 ¥0
    expect(feeStats(makeDeal({ totalReceived: null }))).toEqual({ received: '¥0', invoiced: '¥0', unpaid: null })
  })

  it('railFacts：抽屉同款要素去掉同卡重复的收费方式 / 风险比例 / 代理阶段，其余保留', () => {
    const facts = railFacts(makeDeal({ specified: '2025-03-01', from: '2025-03-12', stages: ['一审', '二审'], no: 'OA-1' }))
    const keys = facts.map(([k]) => k)
    expect(keys).not.toContain('收费方式')
    expect(keys).not.toContain('风险比例')
    expect(keys).not.toContain('代理阶段')
    expect(keys).toEqual(expect.arrayContaining(['指定日期', '签订日期', '建档编号', 'OA 编号']))
  })

  it('railParties：我方在前，firstOther 指向首个对方（全是我方 / 全是对方时为 -1 或 0）', () => {
    const { rows, firstOther } = railParties(makeDeal())
    expect(rows.map((p) => [p.name, p.ours])).toEqual([
      ['某银行', true],
      ['某公司', false],
      ['某五金', false],
    ])
    expect(firstOther).toBe(1)
    expect(railParties(makeDeal({ partiesAll: [] })).firstOther).toBe(-1)
    expect(
      railParties(makeDeal({ partiesAll: [{ name: '甲', role: '对方', idno: '', legalRep: '', phone: '', address: '', ours: false }] })).firstOther,
    ).toBe(0)
  })
})
