// @vitest-environment jsdom
/**
 * UiActionBanner 测试（jsdom）。
 *
 * 这条横幅是「AI 让页面动了一下」的唯一可见证据（执行结果不回传模型、也不进转录），
 * 所以关键不变量都在这里钉住：
 * - 有在飞的动作才出现，文案带动作中文名；`role=status` + `aria-live=polite`
 * - 「停下」是真实按钮，点了调 `abortUiActions`
 * - 终态（ok）停 1.2 秒才淡出（落完就消失，律师会以为「什么都没发生」）
 * - 失败态不淡出（失败必须留得住，直到下一次动作顶掉它）
 * - 单栏不标来源，多栏才加 `agent：` 前缀（照 approval-question 的 laneAgent 口径）
 *
 * store 打桩照 ApprovalCard.dom.test.tsx 的范式：假 store 是普通对象，组件按
 * selector 取字段，所以状态要在 render 之前摆好。
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const storeMock = vi.hoisted(() => ({
  uiToolRuns: {} as Record<string, { name: string; state: string; startedAt: number; endedAt?: number }>,
  /** 本轮勾了几栏（>1 = 多答）：横幅据此决定要不要标来源 */
  answerAgents: [] as string[],
  abortUiActions: vi.fn(),
}))
vi.mock('../store', () => ({
  useCopilot: (sel: (s: typeof storeMock) => unknown) => sel(storeMock),
}))
// 清单是后端 manifest 的生成物：横幅只用到 title，给一份最小的，免得后端改文案把这里带红
vi.mock('../ui-tools', () => ({
  UI_TOOL_SPECS: [{ name: 'ui_navigate', title: '跳转页面' }],
}))

import { UiActionBanner } from './UiActionBanner'

/** 一条运行记录（默认「在飞」） */
function run(state: 'pending' | 'running' | 'ok' | 'error' | 'aborted' = 'running') {
  return { name: 'ui_navigate', state, startedAt: Date.now() }
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers()
  storeMock.uiToolRuns = {}
  storeMock.answerAgents = []
})

afterEach(() => {
  vi.useRealTimers()
})

describe('UiActionBanner：出现与文案', () => {
  it('在飞动作：显示「AI 正在操作：跳转页面」，带 role=status 与 aria-live', () => {
    storeMock.uiToolRuns = { c1: run('running') }
    const { container } = render(<UiActionBanner />)

    const banner = screen.getByRole('status')
    expect(banner.textContent).toContain('AI 正在操作：跳转页面')
    expect(banner.getAttribute('aria-live')).toBe('polite')
    container.remove()
  })

  it('点「停下」调 abortUiActions（真实按钮，不是可点的 div）', () => {
    storeMock.uiToolRuns = { c1: run('running') }
    const { container } = render(<UiActionBanner />)

    fireEvent.click(screen.getByRole('button', { name: '停下' }))

    expect(storeMock.abortUiActions).toHaveBeenCalledTimes(1)
    container.remove()
  })

  it('没有运行记录时不渲染', () => {
    const { container } = render(<UiActionBanner />)
    expect(container.textContent).toBe('')
    container.remove()
  })
})

describe('UiActionBanner：淡出', () => {
  it('ok 后 1.2 秒淡出：1 秒时还在，1.6 秒后消失', () => {
    storeMock.uiToolRuns = { c1: run('ok') }
    const { container } = render(<UiActionBanner />)
    expect(container.textContent).toContain('AI 已完成：跳转页面')
    // 终态不再给「停下」（动作已经落完，点了也没有可挡的东西）
    expect(screen.queryByRole('button', { name: '停下' })).toBeNull()

    act(() => {
      vi.advanceTimersByTime(1_000)
    })
    expect(screen.queryByRole('status')).not.toBeNull()

    act(() => {
      vi.advanceTimersByTime(600)
    })
    expect(screen.queryByRole('status')).toBeNull()
    container.remove()
  })

  it('失败态不淡出（失败必须留得住）', () => {
    storeMock.uiToolRuns = { c1: run('error') }
    const { container } = render(<UiActionBanner />)
    expect(container.textContent).toContain('AI 操作失败：跳转页面')

    act(() => {
      vi.advanceTimersByTime(3_000)
    })

    expect(screen.queryByRole('status')?.textContent).toContain('AI 操作失败：跳转页面')
    container.remove()
  })
})

describe('UiActionBanner：多栏来源', () => {
  it('单栏轮次不标 agent（没有第二栏可分，前缀只是噪音）', () => {
    storeMock.answerAgents = ['pi']
    storeMock.uiToolRuns = { c1: run('running') }
    const { container } = render(<UiActionBanner agent="pi" />)

    expect(container.textContent).not.toContain('pi：')
    expect(container.textContent).toContain('AI 正在操作：跳转页面')
    container.remove()
  })

  it('多栏轮次标来源', () => {
    storeMock.answerAgents = ['pi', 'dsh']
    storeMock.uiToolRuns = { c1: run('running') }
    const { container } = render(<UiActionBanner agent="pi" />)

    expect(container.textContent).toContain('pi：AI 正在操作：跳转页面')
    container.remove()
  })
})
