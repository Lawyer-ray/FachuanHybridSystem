// @vitest-environment jsdom
/**
 * RevisionWalkCard：逐条采纳修订（从第 1 条开始，一条一条停下问「采纳还是驳回」）。
 *
 * 为什么不一次性「全部采纳」：跨境合同的修订都要落到对方还价上，律师真正的工作
 * 是逐条拍板，且中途会被打断、下次接着走。所以断言集中在：
 * - 未开始时只有入口，不预设当前条
 * - 开始后停在第一条未决的前一条，进度条按已走比例
 * - 「采纳/驳回」把 (id, verdict) 交给调用方（状态由父级持有，便于中断续走）
 * - 全部走完后收尾成汇总，不出现「第 6 / 5 条」
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DEMO_TH_CONTRACT_REVISIONS } from '../../demo-nonlit'
import { nextRevision, walkStats } from './crossborder-domain'
import { RevisionWalkCard } from './RevisionWalkCard'

const REVS = DEMO_TH_CONTRACT_REVISIONS

/** 与 RevisionWalkCard 的 props 同签名：逐条拍板的回调形状各不同，混成一个会丢掉参数类型 */
interface WalkHandlers {
  onDecide: (id: string, verdict: 'accept' | 'reject') => void
  onReset: () => void
  onPickRev: (id: string) => void
}

function setup(decided: Record<string, 'accept' | 'reject'> = {}, on: Partial<WalkHandlers> = {}) {
  const handlers = { onDecide: vi.fn(), onReset: vi.fn(), onPickRev: vi.fn(), ...on }
  const view = render(<RevisionWalkCard decided={decided} {...handlers} />)
  return { ...handlers, ...view }
}

describe('未开始', () => {
  it('显示「第 1 / N 条」与入口说明，不预设当前条', () => {
    setup()
    expect(screen.getByText(`第 1 / ${REVS.length} 条`)).toBeTruthy()
    expect(screen.getByText(`${REVS.length} 条修订等你逐条拍板`)).toBeTruthy()
    expect(screen.queryByText('待拍板')).toBeNull()
  })

  it('未开始时没有「跳到某条」（没走起来跳没意义）', () => {
    setup()
    expect(screen.queryByRole('button', { name: /跳到某条/ })).toBeNull()
  })
})

describe('走查中', () => {
  function started(decided: Record<string, 'accept' | 'reject'> = {}) {
    const s = setup(decided)
    fireEvent.click(screen.getByRole('button', { name: /开始逐条走/ }))
    return s
  }

  it('停在第一条未决修订上，显示待拍板标签与原文/改法', () => {
    started()
    const current = nextRevision(REVS, {})!
    expect(screen.getByText('待拍板')).toBeTruthy()
    expect(screen.getByText(current.original)).toBeTruthy()
    expect(screen.getByText(current.suggested)).toBeTruthy()
  })

  it('进度条宽度 = 已走比例', () => {
    const decided = { [REVS[0]!.id]: 'accept' as const }
    const { container } = started(decided)
    const bar = container.querySelector('.h-\\[5px\\] > div') as HTMLElement
    expect(bar.style.width).toBe(`${Math.round((1 / REVS.length) * 100)}%`)
  })

  it('「采纳这条」传 (id, accept)', () => {
    const { onDecide } = started()
    const current = nextRevision(REVS, {})!
    fireEvent.click(screen.getByRole('button', { name: /采纳这条/ }))
    expect(onDecide).toHaveBeenCalledWith(current.id, 'accept')
  })

  it('「驳回」传 (id, reject)', () => {
    const { onDecide } = started()
    const current = nextRevision(REVS, {})!
    fireEvent.click(screen.getByRole('button', { name: /驳回/ }))
    expect(onDecide).toHaveBeenCalledWith(current.id, 'reject')
  })

  it('已决定但未走完时给「已采纳 / 已驳回 / 还剩」摘要', () => {
    const decided = { [REVS[0]!.id]: 'accept' as const, [REVS[1]!.id]: 'reject' as const }
    started(decided)
    expect(screen.getByText(`已采纳 ${walkStats(REVS, decided).accepted}`)).toBeTruthy()
    expect(screen.getByText(`已驳回 ${walkStats(REVS, decided).rejected}`)).toBeTruthy()
    expect(screen.getByText(`还剩 ${REVS.length - 2} 条`)).toBeTruthy()
  })

  it('「跳到某条」展开索引，点一条把 id 交给调用方并收起', () => {
    const { onPickRev } = started()
    fireEvent.click(screen.getByRole('button', { name: /跳到某条/ }))
    const target = REVS[2]!
    fireEvent.click(screen.getByText(target.title))
    expect(onPickRev).toHaveBeenCalledWith(target.id)
    expect(screen.queryByRole('button', { name: /跳到某条/ })).toBeTruthy()
  })

  it('无外国法依据的那条明确写「需律师判断」', () => {
    const unverified = REVS.find((r) => !r.verified)
    if (!unverified) return
    const decided: Record<string, 'accept' | 'reject'> = {}
    for (const r of REVS) if (r.id !== unverified.id) decided[r.id] = 'accept'
    started(decided)
    expect(screen.getByText('无外国法依据 · 需律师判断')).toBeTruthy()
  })
})

describe('走完', () => {
  const allDone = Object.fromEntries(REVS.map((r, i) => [r.id, i % 2 === 0 ? 'accept' : 'reject'])) as Record<
    string,
    'accept' | 'reject'
  >

  it('收尾成汇总，不出现「第 N+1 / N 条」', () => {
    setup(allDone)
    fireEvent.click(screen.getByRole('button', { name: /开始逐条走/ }))
    const stats = walkStats(REVS, allDone)
    expect(screen.getByText(`已走完：采纳 ${stats.accepted} 条 / 驳回 ${stats.rejected} 条`)).toBeTruthy()
    expect(screen.queryByText(`第 ${REVS.length + 1} / ${REVS.length} 条`)).toBeNull()
    // 走完后不再有「待拍板」区块
    expect(screen.queryByText('待拍板')).toBeNull()
  })

  it('汇总里每条可回看（点一条把 id 交回调用方）', () => {
    const { onPickRev } = setup(allDone)
    fireEvent.click(screen.getByRole('button', { name: /开始逐条走/ }))
    fireEvent.click(screen.getByText(REVS[0]!.title))
    expect(onPickRev).toHaveBeenCalledWith(REVS[0]!.id)
  })

  it('说明采纳与驳回各自去向', () => {
    const stats = walkStats(REVS, allDone)
    setup(allDone)
    fireEvent.click(screen.getByRole('button', { name: /开始逐条走/ }))
    expect(
      screen.getByText(`采纳的 ${stats.accepted} 条会写进修订稿；驳回的 ${stats.rejected} 条留在谈判清单里，对方还价可再拉回来。`),
    ).toBeTruthy()
  })
})

describe('重新走', () => {
  it('「重新走」交给调用方清空进度', () => {
    const { onReset } = setup({ [REVS[0]!.id]: 'accept' })
    fireEvent.click(screen.getByRole('button', { name: /重新走/ }))
    expect(onReset).toHaveBeenCalledTimes(1)
  })
})
