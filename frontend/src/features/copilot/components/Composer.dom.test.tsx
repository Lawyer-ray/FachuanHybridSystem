// @vitest-environment jsdom
/**
 * TurnStatsView 与 Composer 测试（jsdom）。
 *
 * TurnStatsView：流式中显示 ≈ tok/s、结束后显示精确 tokens 与平均速度、
 * 无数据时不渲染。Composer：Enter 发送、Shift+Enter 换行、IME 组合中不发送。
 */
import { fireEvent, render, within } from '@testing-library/react'
import { act } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const copilotState = vi.hoisted(() => ({
  streaming: false,
  queuedSteers: [] as string[],
  turnStats: {
    firstDeltaAt: null as number | null,
    lastDeltaAt: null as number | null,
    doneAt: null as number | null,
    estTokens: 0,
    exactTokens: null as number | null,
    samples: [] as number[],
  },
  send: vi.fn(),
  stop: vi.fn(),
  steer: vi.fn(),
  revokeQueuedSteers: vi.fn(),
  submitTask: vi.fn(),
}))

vi.mock('../store', () => ({
  useCopilot: Object.assign(
    (selector: (s: typeof copilotState) => unknown) => selector(copilotState),
    { getState: () => copilotState },
  ),
}))

import { TurnStatsView } from './TurnStatsView'
import { Composer } from './Composer'

beforeEach(() => {
  copilotState.streaming = false
  copilotState.queuedSteers = []
  copilotState.send = vi.fn()
  copilotState.stop = vi.fn()
  copilotState.steer = vi.fn()
  copilotState.revokeQueuedSteers = vi.fn()
  copilotState.submitTask = vi.fn()
  copilotState.turnStats = {
    firstDeltaAt: null,
    lastDeltaAt: null,
    doneAt: null,
    estTokens: 0,
    exactTokens: null,
    samples: [],
  }
})

afterEach(() => {
  vi.useRealTimers()
})

describe('TurnStatsView（结束后）', () => {
  it('无 doneAt 时不渲染', () => {
    const { container } = render(<TurnStatsView />)
    expect(container.textContent).toBe('')
    container.remove()
  })

  it('显示精确 tokens 与平均速度、用时', () => {
    copilotState.turnStats = {
      firstDeltaAt: 1000,
      lastDeltaAt: 3000,
      doneAt: 4000,
      estTokens: 120,
      exactTokens: 150,
      samples: [],
    }
    const { container } = render(<TurnStatsView />)
    const text = container.textContent ?? ''
    expect(text).toContain('150 tokens')
    expect(text).toContain('平均')
    expect(text).toContain('tok/s')
    // 用时 3s（4000-1000）
    expect(text).toContain('3.0s')
    container.remove()
  })

  it('无精确计数时用估算值并加 ≈ 前缀', () => {
    copilotState.turnStats = {
      firstDeltaAt: 0,
      lastDeltaAt: 2000,
      doneAt: 2000,
      estTokens: 80,
      exactTokens: null,
      samples: [],
    }
    const { container } = render(<TurnStatsView />)
    expect(container.textContent).toContain('≈')
    expect(container.textContent).toContain('80 tokens')
    container.remove()
  })

  it('用时超过 100s 时不显示小数', () => {
    copilotState.turnStats = {
      firstDeltaAt: 0,
      lastDeltaAt: 200_000,
      doneAt: 200_000,
      estTokens: 10,
      exactTokens: 10,
      samples: [],
    }
    const { container } = render(<TurnStatsView />)
    expect(container.textContent).toContain('200s')
    container.remove()
  })
})

describe('TurnStatsView（流式中）', () => {
  it('无数据时不渲染', () => {
    copilotState.streaming = true
    const { container } = render(<TurnStatsView />)
    expect(container.textContent).toBe('')
    container.remove()
  })

  it('有样本时以 250ms 刷新显示 ≈ tok/s', () => {
    vi.useFakeTimers()
    copilotState.streaming = true
    const now = Date.now()
    copilotState.turnStats = {
      firstDeltaAt: now - 1000,
      lastDeltaAt: now,
      doneAt: null,
      estTokens: 50,
      exactTokens: null,
      samples: [now - 1000, now - 500, now],
    }
    const { container } = render(<TurnStatsView />)
    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(container.textContent).toContain('tok/s')
    container.remove()
  })
})

describe('Composer', () => {
  it('Enter 发送并清空输入', () => {
    const { container } = render(<Composer />)
    const box = within(container).getByRole('textbox') as HTMLTextAreaElement
    fireEvent.change(box, { target: { value: '你好' } })
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(copilotState.send).toHaveBeenCalledWith('你好')
    container.remove()
  })

  it('Shift+Enter 换行不发送', () => {
    const { container } = render(<Composer />)
    const box = within(container).getByRole('textbox') as HTMLTextAreaElement
    fireEvent.change(box, { target: { value: '你好' } })
    fireEvent.keyDown(box, { key: 'Enter', shiftKey: true })
    expect(copilotState.send).not.toHaveBeenCalled()
    container.remove()
  })

  it('空白输入不发送', () => {
    const { container } = render(<Composer />)
    const box = within(container).getByRole('textbox') as HTMLTextAreaElement
    fireEvent.change(box, { target: { value: '   ' } })
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(copilotState.send).not.toHaveBeenCalled()
    container.remove()
  })

  it('IME 组合中按 Enter 不发送（中文候选确认）', () => {
    const { container } = render(<Composer />)
    const box = within(container).getByRole('textbox') as HTMLTextAreaElement
    fireEvent.change(box, { target: { value: '你好' } })
    fireEvent.keyDown(box, { key: 'Enter', isComposing: true })
    expect(copilotState.send).not.toHaveBeenCalled()
    container.remove()
  })

  it('流式中显示停止按钮，点击调用 stop；输入框保持可用', () => {
    copilotState.streaming = true
    const { container } = render(<Composer />)
    fireEvent.click(within(container).getByRole('button', { name: '停止生成' }))
    expect(copilotState.stop).toHaveBeenCalled()
    // 流式中仍可插话：textarea 未禁用，占位符切为插话提示
    const box = within(container).getByRole('textbox') as HTMLTextAreaElement
    expect(box.disabled).toBe(false)
    expect(box.placeholder).toContain('插话')
    container.remove()
  })

  it('流式中 Enter 发送的是插话（steer）而不是新消息', () => {
    copilotState.streaming = true
    const { container } = render(<Composer />)
    const box = within(container).getByRole('textbox') as HTMLTextAreaElement
    fireEvent.change(box, { target: { value: '补充：只要近一个月' } })
    fireEvent.keyDown(box, { key: 'Enter' })
    expect(copilotState.steer).toHaveBeenCalledWith('补充：只要近一个月')
    expect(copilotState.send).not.toHaveBeenCalled()
    container.remove()
  })

  it('流式中有已插话时显示计数与撤回按钮', () => {
    copilotState.streaming = true
    copilotState.queuedSteers = ['插话一', '插话二']
    const { container } = render(<Composer />)
    expect(container.textContent).toContain('已插话 2 条')
    fireEvent.click(within(container).getByRole('button', { name: '撤回插话' }))
    expect(copilotState.revokeQueuedSteers).toHaveBeenCalled()
    container.remove()
  })

  it('后台运行模式：提交走 submitTask 并自动退出模式', () => {
    const { container } = render(<Composer />)
    const toggle = within(container).getByRole('button', { name: '切换为后台运行' })
    fireEvent.click(toggle)
    const box = within(container).getByRole('textbox') as HTMLTextAreaElement
    expect(box.placeholder).toContain('后台运行')
    fireEvent.change(box, { target: { value: '梳理本案材料' } })
    fireEvent.click(within(container).getByRole('button', { name: '提交后台任务' }))
    expect(copilotState.submitTask).toHaveBeenCalledWith('梳理本案材料')
    expect(copilotState.send).not.toHaveBeenCalled()
    // 提交后模式自动退出，下一次输入回到常规发送
    expect(box.placeholder).not.toContain('后台运行')
    container.remove()
  })

  it('非流式时发送按钮在空输入下禁用', () => {
    const { container } = render(<Composer />)
    const btn = within(container).getByRole('button', { name: '发送' }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    container.remove()
  })
})
