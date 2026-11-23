// @vitest-environment jsdom
/**
 * TurnStatsView（jsdom）：流式中显示 ≈ tok/s、结束后显示精确 tokens 与平均速度、
 * 无数据时不渲染。
 *
 * 从 `Composer.dom.test.tsx` 拆出——之前两组 describe 与 Composer 的三组混在同一个
 * 文件里，而按「同名测试文件」找 TurnStatsView 的回归面只能找到组件本体。断言逐字
 * 未改，只搬了文件与随之同行的那份 store 替身（`turnStats` / `streaming`）。
 */
import { act } from 'react'
import { render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const copilotState = vi.hoisted(() => ({
  streaming: false,
  turnStats: {
    firstDeltaAt: null as number | null,
    lastDeltaAt: null as number | null,
    doneAt: null as number | null,
    estTokens: 0,
    exactTokens: null as number | null,
    samples: [] as number[],
  },
}))

vi.mock('../store', () => ({
  useCopilot: Object.assign(
    (selector: (s: typeof copilotState) => unknown) => selector(copilotState),
    { getState: () => copilotState },
  ),
}))

import { TurnStatsView } from './TurnStatsView'

beforeEach(() => {
  copilotState.streaming = false
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
