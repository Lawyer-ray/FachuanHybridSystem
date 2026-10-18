import { describe, expect, it } from 'vitest'

import type { ContractReminder, DealCase, ReminderOut, WorkbenchDeal } from '../../types'
import {
  ambiguousStages,
  buildDeadlines,
  caseMetaParts,
  chainSteps,
  chainSummary,
  contactGroups,
  dueLabel,
  headerMetaParts,
  legalStatusGroups,
  moneyRows,
  needsVirtualExec,
  orderChain,
  timelineEntries,
} from './detail-domain'

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

describe('程序链', () => {
  it('orderChain：收案日期升序、同日按 id，缺日期排最前', () => {
    const out = orderChain([
      makeCase({ id: 3, from: '2026-03-05', proc: '二审' }),
      makeCase({ id: 1, from: '2025-03-17', proc: '一审' }),
      makeCase({ id: 2, from: '2025-03-17', proc: '保全' }),
      makeCase({ id: 9, from: '', proc: '未立案' }),
    ])
    expect(out.map((c) => c.id)).toEqual([9, 1, 2, 3])
  })

  it('needsVirtualExec：民商事且无执行案才显示；刑事 / 非诉 / 空链 / 已有执行均不显示', () => {
    const chain = [makeCase({ proc: '一审', done: true }), makeCase({ id: 2, proc: '二审' })]
    expect(needsVirtualExec('civil', chain)).toBe(true)
    expect(needsVirtualExec('labor', chain)).toBe(true)
    expect(needsVirtualExec('criminal', chain)).toBe(false)
    expect(needsVirtualExec('advisor', chain)).toBe(false)
    expect(needsVirtualExec('civil', [])).toBe(false)
    expect(needsVirtualExec('civil', [...chain, makeCase({ id: 3, proc: '执行' })])).toBe(false)
  })

  it('chainSteps：已结=done / 在办=cur，副文案拼状态与机构，虚节点追加在尾', () => {
    const steps = chainSteps(
      [makeCase({ id: 1, proc: '一审', done: true, auth: '南海法院' }), makeCase({ id: 2, proc: '二审' })],
      true,
    )
    expect(steps).toEqual([
      { key: 'c1', caseId: 1, stage: '一审', sub: '已结 · 南海法院', state: 'done' },
      { key: 'c2', caseId: 2, stage: '二审', sub: '在办', state: 'cur' },
      { key: 'exec', caseId: null, stage: '执行', sub: '未启动', state: 'todo' },
    ])
  })

  it('chainSummary：计数 + 相邻同阶段合并；空链空串', () => {
    expect(chainSummary([])).toBe('')
    expect(
      chainSummary([makeCase({ proc: '一审' }), makeCase({ id: 2, proc: '一审' }), makeCase({ id: 3, proc: '二审' })]),
    ).toBe('3 个案件 · 一审 → 二审')
  })

  it('ambiguousStages：只有出现 ≥2 次的阶段进集合', () => {
    const s = ambiguousStages([makeCase({ proc: '一审' }), makeCase({ id: 2, proc: '一审' }), makeCase({ id: 3, proc: '二审' })])
    expect([...s]).toEqual(['一审'])
  })
})

describe('案件节', () => {
  it('caseMetaParts：空值不出片段，机构/标的/保全加粗', () => {
    expect(caseMetaParts(makeCase())).toEqual([])
    expect(
      caseMetaParts(makeCase({ auth: '佛山中院', from: '2026-03-05', cause: '金融借款', target: 3200000, preserv: 0 })),
    ).toEqual([
      { v: '佛山中院', strong: true },
      { k: '收案', v: '2026-03-05' },
      { v: '金融借款' },
      { k: '标的', v: '¥3,200,000', strong: true },
    ])
  })

  it('legalStatusGroups：按地位分组保序、空名跳过、无地位归「当事人」', () => {
    expect(
      legalStatusGroups(
        makeCase({
          parties: [
            { status: '原告', name: '甲' },
            { status: '被告', name: '乙' },
            { status: '被告', name: '丙' },
            { status: '', name: '丁' },
            { status: '被告', name: '' },
          ],
        }),
      ),
    ).toEqual([
      { status: '原告', names: ['甲'] },
      { status: '被告', names: ['乙', '丙'] },
      { status: '当事人', names: ['丁'] },
    ])
  })

  it('timelineEntries：倒序日志翻成升序叙事，日期取前 10 位', () => {
    const c = makeCase({
      logs: [
        { when: '2026-03-05T10:00', who: '周明', text: '二审立案', attN: 0, rem: '', remToday: false },
        { when: '2026-02-02T09:30', who: '黄崧', text: '收到上诉状', attN: 2, rem: '', remToday: false },
      ],
    })
    expect(timelineEntries(c).map((e) => [e.date, e.text, e.who, e.attN])).toEqual([
      ['2026-02-02', '收到上诉状', '黄崧', 2],
      ['2026-03-05', '二审立案', '周明', 0],
    ])
  })
})

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

  it('moneyRows：标的/保全取链上首个有值案件，费用拼收费方式，空值不出行', () => {
    const rows = moneyRows(makeDeal(), [makeCase({ target: null }), makeCase({ id: 2, target: 3200000, preserv: 1600000 })])
    expect(rows).toEqual([
      ['标的额', '¥3,200,000'],
      ['保全金额', '¥1,600,000'],
      ['律师费', '¥50,000 · 半风险'],
      ['风险比例', '8%'],
      ['已收款', '¥50,000'],
    ])
    expect(moneyRows(makeDeal({ amount: null, fee: '', riskRate: null, totalReceived: null }), [])).toEqual([])
    // 没填金额只有收费方式：标签改「收费方式」，不把方式冒充成律师费数值
    expect(moneyRows(makeDeal({ amount: null, fee: '固定收费', riskRate: null, totalReceived: null }), [])).toEqual([
      ['收费方式', '固定收费'],
    ])
  })
})

describe('页头', () => {
  it('headerMetaParts：类型/状态加粗，我方 → 多个对方顿号连接，建档/主办尾随', () => {
    expect(headerMetaParts(makeDeal())).toEqual([
      { v: '民商事', strong: true },
      { v: '在办', strong: true },
      { k: '我方', v: '某银行 → 某公司、某五金' },
      { k: '建档', v: '2025_MS_HT_0031' },
      { k: '主办', v: '黄崧' },
    ])
  })

  it('headerMetaParts：没有我方当事人则不出该片段', () => {
    const parts = headerMetaParts(makeDeal({ partiesAll: [], filingNo: '', primary: '' }))
    expect(parts).toEqual([{ v: '民商事', strong: true }, { v: '在办', strong: true }])
  })
})
