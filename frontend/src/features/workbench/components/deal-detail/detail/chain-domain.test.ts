import { describe, expect, it } from 'vitest'

import type { DealCase } from '../../../types'
import {
  ambiguousStages,
  buildStagePlan,
  chainSteps,
  chainSummary,
  nextStage,
  orderChain,
  planCases,
} from './chain-domain'

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
