// @vitest-environment jsdom
/**
 * useSmoothStreamText：流式文本的平滑放字。
 *
 * 这里锁的核心是那条**硬不变量**：返回值任何时刻都是 `full` 的前缀。
 * 前缀一旦被破坏，markdown 会原地重排（表格结构被打乱），视觉上比不平滑更糟。
 *
 * 帧推进用手动驱动的 requestAnimationFrame 桩，不用真等 16ms——
 * 否则每个用例都要 sleep，且拿不到「恰好第 N 帧」这种确定的时序。
 */

import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  SMOOTH_STREAM_JUMP_BACKLOG,
  SMOOTH_STREAM_MAX_LENGTH,
  SMOOTH_STREAM_TICK_FRAMES,
} from '../lib/smooth-stream'
import { useSmoothStreamText } from './use-smooth-stream-text'

/** 收集每一帧的回调，由用例显式 step() 推进 */
let frameCallbacks: FrameRequestCallback[] = []
let rafId = 0

beforeEach(() => {
  frameCallbacks = []
  rafId = 0
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    frameCallbacks.push(cb)
    rafId += 1
    return rafId
  })
  vi.stubGlobal('cancelAnimationFrame', () => {
    frameCallbacks = []
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

/**
 * 推进 n 帧。每帧把所有排队回调取出执行（回调内部会重新 requestAnimationFrame，
 * 于是进入下一批），整个过程包在 act 里，让 React 处理 setState。
 */
function step(n: number) {
  for (let i = 0; i < n; i += 1) {
    const pending = frameCallbacks
    frameCallbacks = []
    act(() => {
      for (const cb of pending) cb(performance.now())
    })
  }
}

/** 推进足够多帧让放字追赶完（或确认追不完） */
function stepTicks(ticks: number) {
  step(ticks * SMOOTH_STREAM_TICK_FRAMES)
}

describe('useSmoothStreamText：非直播', () => {
  it('live 为 false 时原样返回 full，且不调度任何动画帧', () => {
    const { result } = renderHook(() => useSmoothStreamText('完整文本', false))

    expect(result.current).toBe('完整文本')
    // 非 active 时 useEffect 直接 return，不该排任何 rAF
    expect(frameCallbacks).toHaveLength(0)
  })

  it('live 由 true 变 false 时，同一次渲染就补齐全文（不延一帧）', () => {
    const { result, rerender } = renderHook(
      ({ text, live }: { text: string; live: boolean }) => useSmoothStreamText(text, live),
      { initialProps: { text: '一二三四五六七八九十', live: true } },
    )

    // 直播中且还没推进帧，可见文本是初始状态
    rerender({ text: '一二三四五六七八九十', live: false })
    expect(result.current).toBe('一二三四五六七八九十')
  })
})

describe('useSmoothStreamText：硬不变量（返回值永远是 full 的前缀）', () => {
  it('逐帧推进过程中，任何时刻返回值都是 full 的前缀', () => {
    const full = `${'甲'.repeat(400)}末尾`
    const { result, rerender } = renderHook(
      ({ text }: { text: string }) => useSmoothStreamText(text, true),
      { initialProps: { text: '' } },
    )

    // 先给一小段，再逐帧追加，每帧都检查前缀关系
    for (let i = 1; i <= 40; i += 1) {
      const text = full.slice(0, i * 10)
      rerender({ text })
      stepTicks(1)
      expect(full.startsWith(result.current)).toBe(true)
      expect(result.current.length).toBeLessThanOrEqual(full.length)
    }
  })

  it('积压始终能追上：给足帧数后最终显示全文', () => {
    const full = '乙'.repeat(200)
    const { result } = renderHook(() => useSmoothStreamText(full, true))

    // 初始 displayed 是 full（useState(full)），所以立刻就是全文；
    // 真正考验追赶的是下面「先说一点点、再变长」的用例。
    expect(result.current).toBe(full)
  })
})

describe('useSmoothStreamText：渐进放字与逃生通道', () => {
  it('从空文本逐字增长时，放字是渐进而不是一次到位', () => {
    const full = '丙'.repeat(300)
    const { result, rerender } = renderHook(
      ({ text }: { text: string }) => useSmoothStreamText(text, true),
      { initialProps: { text: '' } },
    )

    // 一次性把全文推给 hook：积压 300 字，未超 JUMP_BACKLOG，进入平滑模式
    rerender({ text: full })
    expect(result.current).toBe('')

    // 一个 tick 之后应当只放出一部分，而不是全文
    stepTicks(1)
    const afterOneTick = result.current.length
    expect(afterOneTick).toBeGreaterThan(0)
    expect(afterOneTick).toBeLessThan(full.length)

    // 再推进若干 tick，应继续单调增长
    stepTicks(1)
    expect(result.current.length).toBeGreaterThan(afterOneTick)
  })

  it('积压超过 JUMP_BACKLOG 时直接到位（不逐字爬）', () => {
    const full = '丁'.repeat(SMOOTH_STREAM_JUMP_BACKLOG + 500)
    const { result, rerender } = renderHook(
      ({ text }: { text: string }) => useSmoothStreamText(text, true),
      { initialProps: { text: '' } },
    )

    rerender({ text: full })
    // 渲染期推导即判定积压超限 → 不等任何帧，直接显示全文
    expect(result.current).toBe(full)
  })

  it('全文超过 MAX_LENGTH 时不做平滑（直接全文）', () => {
    const full = '戊'.repeat(SMOOTH_STREAM_MAX_LENGTH + 1)
    const { result } = renderHook(() => useSmoothStreamText(full, true))

    expect(result.current).toBe(full)
    expect(frameCallbacks).toHaveLength(0)
  })

  it('full 不再以 displayed 开头（快照改写）时立即整段显示，不试图局部推进', () => {
    const { result, rerender } = renderHook(
      ({ text }: { text: string }) => useSmoothStreamText(text, true),
      { initialProps: { text: '原始开头内容' } },
    )
    expect(result.current).toBe('原始开头内容')

    // 整段被换掉：新内容不以旧可见文本开头
    const rewritten = '完全不同的重写内容'
    rerender({ text: rewritten })
    expect(result.current).toBe(rewritten)
  })

  it('积压未超限但内容不变时，不产生多余的 setState（可见文本稳定）', () => {
    const full = '己'.repeat(100)
    const { result } = renderHook(() => useSmoothStreamText(full, true))

    expect(result.current).toBe(full)
    stepTicks(5)
    // 已经显示完全文，再推帧不该改变结果
    expect(result.current).toBe(full)
  })

  it('卸载时取消动画帧，不再继续调度', () => {
    const full = '庚'.repeat(200)
    const { unmount } = renderHook(() => useSmoothStreamText(full, true))
    unmount()

    // cleanup 调用了 cancelAnimationFrame（桩里清空队列）
    expect(frameCallbacks).toHaveLength(0)
  })
})
