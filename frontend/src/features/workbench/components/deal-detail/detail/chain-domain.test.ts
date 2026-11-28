import { describe, expect, it } from 'vitest'

import type { DealCase } from '../../../types'
import {
  ambiguousStages,
  buildStagePlan,
  caseBranches,
  chainShape,
  chainSteps,
  chainSummary,
  nextStage,
  orderChain,
  planCases,
  trimPlan,
} from './chain-domain'

function makeCase(over: Partial<DealCase> = {}): DealCase {
  return {
    id: 1,
    name: '案件',
    proc: '一审',
    prev: null,
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

describe('形态判定：一个委托下有几条程序线（决定顶部画什么）', () => {
  it('零案 → none；一案件 → single（顶部不画，单案的信息在案件卡上）', () => {
    expect(chainShape(caseBranches([]))).toBe('none')
    expect(chainShape(caseBranches([makeCase({ id: 1 })]))).toBe('single')
  })

  it('322 号形态：一审 prev=劳动仲裁，串成一条线 → chain，线内按程序序而不是收案日期', () => {
    const branches = caseBranches([
      makeCase({ id: 2, proc: '一审', from: '2026-10-12', prev: 1 }),
      makeCase({ id: 1, proc: '劳动仲裁', from: '2026-07-07' }),
    ])
    expect(branches.map((b) => b.map((c) => [c.id, c.proc]))).toEqual([
      [
        [1, '劳动仲裁'],
        [2, '一审'],
      ],
    ])
    expect(chainShape(branches)).toBe('chain')
  })

  it('271 号形态：两个二审、只有一个串了执行 → multi；执行与它自己的二审同线，另一个二审自成一线', () => {
    const branches = caseBranches([
      makeCase({ id: 305, proc: '二审', from: '2026-05-01' }),
      makeCase({ id: 375, proc: '二审', from: '2026-06-01' }),
      makeCase({ id: 361, proc: '执行', from: '2026-09-01', prev: 305 }),
    ])
    expect(chainShape(branches)).toBe('multi')
    // 三个案件一个都不能丢（丢案比画错更严重）
    expect(branches.flat().map((c) => c.id).sort()).toEqual([305, 361, 375])
    const withExec = branches.find((b) => b.some((c) => c.id === 361))!
    expect(withExec.map((c) => c.proc)).toEqual(['二审', '执行'])
    expect(branches.find((b) => b.some((c) => c.id === 375))!.map((c) => c.proc)).toEqual(['二审'])
  })

  it('261 号形态：四个案件一个 prev 都没写 → 四条线（不知道谁接谁，就不替律师猜）', () => {
    const branches = caseBranches([
      makeCase({ id: 293, proc: '一审', done: true, from: '2026-04-07' }),
      makeCase({ id: 294, proc: '一审', done: true, from: '2026-04-07' }),
      makeCase({ id: 387, proc: '执行', from: '2026-10-10' }),
      makeCase({ id: 388, proc: '执行', from: '2026-10-10' }),
    ])
    expect(branches).toHaveLength(4)
    expect(chainShape(branches)).toBe('multi')
  })

  it('series case：14 个互不相干的案件 → multi，每个案件都是一条线（×14 这种进度条没意义）', () => {
    const cases = Array.from({ length: 14 }, (_, i) => makeCase({ id: i + 1, proc: '一审' }))
    const branches = caseBranches(cases)
    expect(branches).toHaveLength(14)
    expect(chainShape(branches)).toBe('multi')
  })

  it('prev 指向本委托以外 / 指向自己 → 按无线处理，案件不会被吞掉', () => {
    const branches = caseBranches([makeCase({ id: 1, prev: 999 }), makeCase({ id: 2, prev: 2 })])
    expect(branches).toHaveLength(2)
    expect(branches.flat().map((c) => c.id).sort()).toEqual([1, 2])
  })

  it('脏数据成环（a.prev=b 且 b.prev=a）不死循环，两个案件归一条线', () => {
    const branches = caseBranches([makeCase({ id: 1, prev: 2 }), makeCase({ id: 2, prev: 1 })])
    expect(branches.map((b) => b.map((c) => c.id))).toEqual([[1, 2]])
  })
})

describe('trimPlan：永远空着的节点不画（勾选的是代理范围，不等于走得到的程序）', () => {
  it('一审已结 + 执行在办、勾了二审 → 中间那个二审不画（它永远不会发生）', () => {
    const plan = buildStagePlan(
      ['一审', '二审', '执行'],
      [makeCase({ id: 1, proc: '一审', done: true }), makeCase({ id: 2, proc: '执行' })],
    )
    expect(plan.map((p) => p.stage)).toEqual(['一审', '二审', '执行'])
    expect(trimPlan(plan).map((p) => p.stage)).toEqual(['一审', '执行'])
    // nextStage 与「最后那个空心节点」仍是同一个程序：两处口径不能分叉
    expect(nextStage(plan)).toBeNull()
  })

  it('最后已启动阶段之后只留紧邻的一个空心节点', () => {
    const plan = buildStagePlan(['一审', '二审', '再审一审', '执行'], [makeCase({ id: 1, proc: '一审' })])
    expect(plan.map((p) => p.stage)).toEqual(['一审', '二审', '再审一审', '执行'])
    expect(trimPlan(plan).map((p) => p.stage)).toEqual(['一审', '二审'])
  })

  it('一个都还没启动 → 原样返回：那是合同约定的代理范围，不是噪音', () => {
    const plan = buildStagePlan(['一审', '二审'], [])
    expect(trimPlan(plan)).toEqual(plan)
  })
})
