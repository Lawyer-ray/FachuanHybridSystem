import { describe, expect, it } from 'vitest'

import type { ContractReminder, DealCase, ReminderOut, WorkbenchDeal } from '../../types'
import {shortDocName, splitLinkText,
  ambiguousStages,
  buildDeadlines,
  buildStagePlan,
  caseMetaParts,
  chainSteps,
  chainSummary,
  crumbName,
  contactGroups,
  dueLabel,
  headerMetaParts,
  legalStatusGroups,
  moneyRows,
  nextStage,
  orderChain,
  planCases,
  railFacts,
  railParties,
  stripEntryParens,
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

/** 日志附件夹具（合并用例按 id 去重） */
const att = (id: number, name = 'a' + id + '.pdf') => ({ id, name, mediaUrl: '/media/x/' + id })

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

describe('程序链（计划 = 合同勾选阶段 ∪ 案件实际阶段，按程序序）', () => {
  it('orderChain：收案日期升序、同日按 id，缺日期排最前', () => {
    const out = orderChain([
      makeCase({ id: 3, from: '2026-03-05', proc: '二审' }),
      makeCase({ id: 1, from: '2025-03-17', proc: '一审' }),
      makeCase({ id: 2, from: '2025-03-17', proc: '保全' }),
      makeCase({ id: 9, from: '', proc: '未立案' }),
    ])
    expect(out.map((c) => c.id)).toEqual([9, 1, 2, 3])
  })

  it('322 号形态：合同按枚举序存「一审、二审、劳动仲裁」，计划按程序序排成 劳动仲裁 → 一审 → 二审，下一步=二审，没有执行', () => {
    const plan = buildStagePlan(
      ['一审', '二审', '劳动仲裁'],
      [makeCase({ id: 1, proc: '劳动仲裁', done: true, from: '2026-07-07' }), makeCase({ id: 2, proc: '一审', from: '2026-10-12' })],
    )
    expect(plan.map((p) => [p.stage, p.state, p.cases.length, p.selected])).toEqual([
      ['劳动仲裁', 'done', 1, true],
      ['一审', 'cur', 1, true],
      ['二审', 'todo', 0, true],
    ])
    expect(nextStage(plan)).toBe('二审')
    expect(plan.some((p) => p.stage === '执行')).toBe(false)
    expect(chainSummary(plan)).toBe('2 个案件 · 劳动仲裁 → 一审')
  })

  it('261 号形态：两个一审已结 + 两个执行在办、勾了二审没立：二审在中间留未启动，不算下一步；分叉阶段计数', () => {
    const plan = buildStagePlan(
      ['一审', '二审', '执行'],
      [
        makeCase({ id: 1, proc: '一审', done: true, from: '2026-04-07' }),
        makeCase({ id: 2, proc: '一审', done: true, from: '2026-04-07' }),
        makeCase({ id: 3, proc: '执行', from: '2026-10-10' }),
        makeCase({ id: 4, proc: '执行', from: '2026-10-10' }),
      ],
    )
    expect(plan.map((p) => [p.stage, p.state, p.cases.length])).toEqual([
      ['一审', 'done', 2],
      ['二审', 'todo', 0],
      ['执行', 'cur', 2],
    ])
    expect(nextStage(plan)).toBeNull()
    expect([...ambiguousStages(plan)]).toEqual(['一审', '执行'])
    expect(chainSummary(plan)).toBe('4 个案件 · 一审 → 执行')
  })

  it('执行先于一审收案（合同 9 形态）：主列仍按程序序 一审 → 执行，而非收案时间序', () => {
    const plan = buildStagePlan(
      ['一审', '二审', '执行'],
      [makeCase({ id: 1, proc: '执行', from: '2026-03-23' }), makeCase({ id: 2, proc: '一审', from: '2026-08-06' })],
    )
    expect(planCases(plan).map((c) => c.proc)).toEqual(['一审', '执行'])
    expect(nextStage(plan)).toBeNull()
  })

  it('合同一个阶段都没勾：退化为只看案件；案件阶段不在勾选里也照样展示（selected=false）', () => {
    const plan = buildStagePlan([], [makeCase({ id: 1, proc: '二审' })])
    expect(plan).toEqual([{ stage: '二审', state: 'cur', cases: [expect.objectContaining({ id: 1 })], selected: false }])
    expect(nextStage(plan)).toBeNull()

    const drift = buildStagePlan(['一审'], [makeCase({ id: 1, proc: '一审', done: true }), makeCase({ id: 2, proc: '执行' })])
    expect(drift.map((p) => [p.stage, p.selected])).toEqual([
      ['一审', true],
      ['执行', false],
    ])
  })

  it('全部未启动（勾了没立）：下一步取第一个；未知阶段标签排最后', () => {
    expect(nextStage(buildStagePlan(['二审', '一审'], []))).toBe('一审')
    const plan = buildStagePlan(['一审'], [makeCase({ id: 1, proc: '未立案' })])
    expect(plan.map((p) => p.stage)).toEqual(['一审', '未立案'])
  })

  it('chainSteps：首案 id 可跳、单案带机构、多案不带机构只标 ×N、未启动 caseId=null', () => {
    const plan = buildStagePlan(
      ['一审', '二审'],
      [makeCase({ id: 1, proc: '一审', done: true, auth: '南海法院' }), makeCase({ id: 2, proc: '一审', done: true, auth: '顺德法院' })],
    )
    expect(chainSteps(plan)).toEqual([
      { key: '一审', caseId: 1, stage: '一审', sub: '已结', state: 'done', n: 2 },
      { key: '二审', caseId: null, stage: '二审', sub: '未启动', state: 'todo', n: 0 },
    ])
    const single = buildStagePlan([], [makeCase({ id: 5, proc: '一审', auth: '南海法院' })])
    expect(chainSteps(single)[0]).toMatchObject({ caseId: 5, sub: '在办 · 南海法院', n: 1 })
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

  it('legalStatusGroups：按判决书逻辑排序——原告 → 被告 → 第三人，不看出现顺序；未知地位殿后保序', () => {
    expect(
      legalStatusGroups(
        makeCase({
          parties: [
            { status: '被告', name: '乙' },
            { status: '第三人', name: '丙' },
            { status: '原告', name: '甲' },
            { status: '案外人', name: '戊' },
            { status: '案外人', name: '己' },
          ],
        }),
      ),
    ).toEqual([
      { status: '原告', names: ['甲'] },
      { status: '被告', names: ['乙'] },
      { status: '第三人', names: ['丙'] },
      { status: '案外人', names: ['戊', '己'] },
    ])
  })

  it('timelineEntries：倒序日志翻成升序叙事，日期取前 10 位', () => {
    const c = makeCase({
      logs: [
        { id: 2, when: '2026-03-05T10:00', who: '王某某', text: '二审立案', attN: 0, atts: [], rem: '', remToday: false },
        { id: 1, when: '2026-02-02T09:30', who: '李某某', text: '收到上诉状', attN: 2, atts: [att(11), att(12)], rem: '', remToday: false },
      ],
    })
    expect(timelineEntries(c).map((e) => [e.date, e.text, e.who, e.attN])).toEqual([
      ['2026-02-02', '收到上诉状', '李某某', 2],
      ['2026-03-05', '二审立案', '王某某', 0],
    ])
  })

  it('timelineEntries：相同内容自动合并（×N、落最新时间、who 取最新、附件按文件名去重并集）', () => {
    const dup = '收到法院短信：执行款已到账'
    const c = makeCase({
      logs: [
        // 倒序（新 → 旧）：两条同内容 + 一条独立；重放日志附件常同名不同 id
        { id: 5, when: '2026-09-03T10:00', who: '李某某', text: dup, attN: 2, atts: [{ id: 52, name: '裁定书.pdf', mediaUrl: '/media/x52' }, att(51)], rem: '', remToday: false },
        { id: 4, when: '2026-09-02T09:00', who: '系统', text: dup, attN: 2, atts: [{ id: 41, name: '裁定书.pdf', mediaUrl: '/media/x41' }, att(51)], rem: '', remToday: false },
        { id: 3, when: '2026-08-30T09:00', who: '李某某', text: '单独一条', attN: 0, atts: [], rem: '', remToday: false },
      ],
    })
    const out = timelineEntries(c)
    expect(out.map((e) => [e.date, e.text, e.who, e.n])).toEqual([
      ['2026-08-30', '单独一条', '李某某', 1],
      ['2026-09-03', dup, '李某某', 2],
    ])
    const merged = out[1]!
    // 「裁定书.pdf」两条同名只留先到的 id=41，a51 的名字不同保留
    expect(merged.atts.map((a) => a.id)).toEqual([41, 51])
    expect(merged.attN).toBe(2)
    expect(merged.key).toBe('L4')
  })

  it('timelineEntries：单条待合并日志自带两个同名附件时不得重复计入', () => {
    // 回归 2026-10 审查 P0：合并分支的 seenNames 漏 add，同一批 l.atts 内的同名
    // 第二个附件会绕过去重被重复 push（重放日志常带同名不同 id 的附件）
    const dup = '收到法院短信：执行款已到账'
    const c = makeCase({
      logs: [
        // 倒序：较新的一条带两个同名「裁定书.pdf」
        {
          id: 9,
          when: '2026-09-03T10:00',
          who: '系统',
          text: dup,
          attN: 2,
          atts: [att(92, '裁定书.pdf'), att(91, '裁定书.pdf')],
          rem: '',
          remToday: false,
        },
        // 较旧的一条先建立条目
        { id: 8, when: '2026-09-02T09:00', who: '系统', text: dup, attN: 1, atts: [att(81, '其它.pdf')], rem: '', remToday: false },
      ],
    })
    const merged = timelineEntries(c)[0]!
    expect(merged.n).toBe(2)
    // 「裁定书.pdf」只应留一个（先出现的 92），加「其它.pdf」共 2 个
    expect(merged.atts.map((a) => a.name)).toEqual(['其它.pdf', '裁定书.pdf'])
    expect(merged.attN).toBe(2)
  })

  it('timelineEntries：多条日志跨轮次合并时同名附件不重复', () => {
    // 回归 2026-10 审查 P0：合并分支的 seenNames 曾漏 add，导致第二轮之后的
    // 同名附件被重复 push（重放日志常带同名不同 id 的附件）
    const dup = '收到法院短信：执行款已到账'
    const c = makeCase({
      logs: [
        { id: 7, when: '2026-09-04T10:00', who: '李某某', text: dup, attN: 1, atts: [{ id: 73, name: '裁定书.pdf', mediaUrl: '/media/x73' }], rem: '', remToday: false },
        { id: 6, when: '2026-09-03T10:00', who: '系统', text: dup, attN: 1, atts: [{ id: 62, name: '裁定书.pdf', mediaUrl: '/media/x62' }], rem: '', remToday: false },
        { id: 5, when: '2026-09-02T09:00', who: '系统', text: dup, attN: 1, atts: [{ id: 51, name: '裁定书.pdf', mediaUrl: '/media/x51' }], rem: '', remToday: false },
      ],
    })
    const merged = timelineEntries(c)[0]!
    expect(merged.n).toBe(3)
    // 同名附件只保留最早的一条，跨三轮合并不得重复
    expect(merged.atts.map((a) => a.id)).toEqual([51])
    expect(merged.attN).toBe(1)
  })

  it('timelineEntries：三轮合并时每轮新增的不同名附件都要保留', () => {
    const dup = '收到法院短信：执行款已到账'
    const c = makeCase({
      logs: [
        { id: 7, when: '2026-09-04T10:00', who: 'A', text: dup, attN: 2, atts: [att(73, 'c.pdf'), att(71, 'a.pdf')], rem: '', remToday: false },
        { id: 6, when: '2026-09-03T10:00', who: 'B', text: dup, attN: 2, atts: [att(62, 'b.pdf'), att(61, 'a.pdf')], rem: '', remToday: false },
        { id: 5, when: '2026-09-02T09:00', who: 'C', text: dup, attN: 1, atts: [att(51, 'a.pdf')], rem: '', remToday: false },
      ],
    })
    const merged = timelineEntries(c)[0]!
    // 去重按文件名，保留首次出现的 id：a=51（最早）、b=62、c=73
    expect(merged.atts.map((a) => a.name).sort()).toEqual(['a.pdf', 'b.pdf', 'c.pdf'])
    expect(merged.attN).toBe(3)
  })

  it('stripEntryParens：只隐藏长案件名括号，短括号（当事人/年份/备注）保留', () => {
    // 长描述型（≥12 字）→ 隐藏，卡片已标明案件
    expect(stripEntryParens('民事裁定书（张某诉某公司买卖合同纠纷一案）_20260929收.pdf')).toBe(
      '民事裁定书_20260929收.pdf',
    )
    // 嵌套括号（案件名里嵌公司名括号）配平后整体隐藏
    expect(stripEntryParens('账户确认书（张某诉某公司买卖合同纠纷（二审）一案）V1.pdf')).toBe('账户确认书V1.pdf')
    // 短括号是区分信息，必须保留：当事人、年份案号、备注
    expect(stripEntryParens('通知书（王某执行案）_20260414收.pdf')).toBe('通知书（王某执行案）_20260414收.pdf')
    expect(stripEntryParens('（20XX）粤0000执保1号民事裁定书.pdf')).toBe('（20XX）粤0000执保1号民事裁定书.pdf')
    expect(stripEntryParens('2-授权委托书（张某）（某醉驾一案）V1.pdf')).toBe('2-授权委托书（张某）（某醉驾一案）V1.pdf')
    expect(stripEntryParens('【发票】某甲（个人）_20251023.pdf')).toBe('【发票】某甲（个人）_20251023.pdf')
    // 整名都在括号里 / 括号不配对 → 退回原名
    expect(stripEntryParens('（张某诉某公司买卖合同纠纷一案）.pdf')).toBe('（张某诉某公司买卖合同纠纷一案）.pdf')
    expect(stripEntryParens('说明（未闭合.pdf')).toBe('说明（未闭合.pdf')
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

describe('页头', () => {
  it('headerMetaParts：类型/状态加粗，建档尾随；我方→对方与主办不再出现在页头（右栏卡已展示）', () => {
    expect(headerMetaParts(makeDeal())).toEqual([
      { v: '民商事', strong: true },
      { v: '在办', strong: true },
      { k: '建档', v: '2025_MS_HT_0031' },
    ])
  })

  it('headerMetaParts：没有建档号只剩类型与状态', () => {
    const parts = headerMetaParts(makeDeal({ partiesAll: [], filingNo: '', primary: '' }))
    expect(parts).toEqual([{ v: '民商事', strong: true }, { v: '在办', strong: true }])
  })

  it('crumbName：超 18 字截断加省略号，短名原样', () => {
    expect(crumbName('短短的名字')).toBe('短短的名字')
    const long = '某市公路工程质量检测有限责任公司诉广东某交通投资有限公司及第三人某混凝土公司执行异议之诉一案'
    expect(crumbName(long)).toBe('某市公路工程质量检测有限责任公司诉广…')
    expect(crumbName(long).length).toBe(19)
  })
})

describe('shortDocName 附件短名', () => {
  it('去扩展名 + 第一个下划线起的尾巴（生成文书的委托人后缀）', () => {
    expect(shortDocName('民事诉讼风险提示书_test_某某示范公司.pdf')).toBe('民事诉讼风险提示书')
    expect(shortDocName('传票_test_某某示范公司.docx')).toBe('传票')
  })
  it('无下划线只去扩展名；无扩展名原样', () => {
    expect(shortDocName('起诉状.txt')).toBe('起诉状')
    expect(shortDocName('会议纪要')).toBe('会议纪要')
  })
  it('以 _ 开头（截断后为空）回退全名，不让 chip 变空', () => {
    expect(shortDocName('_副本.pdf')).toBe('_副本.pdf')
  })
})

describe('splitLinkText 日志正文链接切分', () => {
  it('法院短信：URL 成段，前后的中文（含紧跟链接的文字）不被吞进 URL', () => {
    const text = '你好，请查收送达文书。点击链接查阅：https://zxfw.court.gov.cn/zxfw/#/index?qdbh=abc123&sdsin=def456请及时查收，逾期视为送达'
    const segs = splitLinkText(text)
    expect(segs[0]).toEqual({ kind: 'text', value: '你好，请查收送达文书。点击链接查阅：' })
    expect(segs[1]?.kind).toBe('url')
    expect(segs[1]?.value).toBe('https://zxfw.court.gov.cn/zxfw/#/index?qdbh=abc123&sdsin=def456')
    expect(segs[2]).toEqual({ kind: 'text', value: '请及时查收，逾期视为送达' })
  })
  it('多个 URL 逐段切开', () => {
    const segs = splitLinkText('先看 https://a.com/x 再看 http://b.com/y')
    expect(segs).toEqual([
      { kind: 'text', value: '先看 ' },
      { kind: 'url', value: 'https://a.com/x' },
      { kind: 'text', value: ' 再看 ' },
      { kind: 'url', value: 'http://b.com/y' },
    ])
  })
  it('无 URL 时整段文本', () => {
    expect(splitLinkText('普通日志，无链接')).toEqual([{ kind: 'text', value: '普通日志，无链接' }])
  })
})
