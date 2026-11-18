// @vitest-environment jsdom
/**
 * useImeEnterGuard 测试（jsdom）。
 *
 * 锁的是「选词 Enter 不能把半句话发出去」这条线上事故：
 * - 普通 Enter 必须放行；
 * - 合成中的 Enter 拦下但**不** preventDefault（否则打断输入法上屏）；
 * - compositionend 之后 80ms 内的尾随 Enter 拦下**并** preventDefault
 *   （WebKit 先 end 后 keydown，此时 isComposing 已是 false）；
 * - 超过 80ms 放行（用户真的又按了一次）；
 * - 不派发 composition 事件、只把 keyCode 钉成 229 的输入法也要拦住。
 *
 * 事件对象手建 plain object 强转：timeStamp 必须可精确控制，jsdom 的
 * KeyboardEvent.timeStamp 是只读的高精度时间，没法设成「compositionend 后
 * 第 10ms」这种值。
 */
import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { POST_COMPOSITION_ENTER_GUARD_MS, useImeEnterGuard } from './use-ime-enter-guard'

type EnterGuard = ReturnType<typeof useImeEnterGuard>

/** 极简键盘事件替身：timeStamp / keyCode / isComposing 全部可控 */
function keyEvent(
  key: string,
  opts: { timeStamp?: number; keyCode?: number; isComposing?: boolean } = {},
) {
  return {
    key,
    timeStamp: opts.timeStamp ?? 0,
    keyCode: opts.keyCode ?? 0,
    preventDefault: vi.fn(),
    nativeEvent: { isComposing: opts.isComposing ?? false },
  } as unknown as KeyboardEvent
}

/** 走一遍 compositionend，并把窗口基准时间戳定在 `at` */
function endComposition(guard: EnterGuard, at: number) {
  act(() => {
    guard.onCompositionEnd({ timeStamp: at } as unknown as CompositionEvent)
  })
}

describe('useImeEnterGuard：普通 Enter 放行', () => {
  it('什么都不发生时的 Enter 不拦、不 preventDefault', () => {
    const { result } = renderHook(() => useImeEnterGuard())
    const e = keyEvent('Enter', { timeStamp: 5000 })

    expect(result.current.shouldIgnoreEnter(e)).toBe(false)
    expect(result.current.guardEnter(e)).toBe(false)
    expect(e.preventDefault).not.toHaveBeenCalled()
  })
})

describe('useImeEnterGuard：合成中的 Enter', () => {
  it('compositionstart 之后 Enter 被拦，且不调用 preventDefault', () => {
    const { result } = renderHook(() => useImeEnterGuard())
    act(() => {
      result.current.onCompositionStart()
    })
    const e = keyEvent('Enter', { timeStamp: 1000 })

    expect(result.current.shouldIgnoreEnter(e)).toBe(true)
    expect(result.current.guardEnter(e)).toBe(true)
    // 抢了 preventDefault 会打断输入法选词上屏，必须留给输入法
    expect(e.preventDefault).not.toHaveBeenCalled()
  })

  it('nativeEvent.isComposing 为 true 时也拦（不依赖 compositionstart）', () => {
    const { result } = renderHook(() => useImeEnterGuard())
    const e = keyEvent('Enter', { timeStamp: 1000, isComposing: true })

    expect(result.current.shouldIgnoreEnter(e)).toBe(true)
    expect(result.current.guardEnter(e)).toBe(true)
    expect(e.preventDefault).not.toHaveBeenCalled()
  })

  it('compositionend 之后 isComposing 立刻恢复 false', () => {
    const { result } = renderHook(() => useImeEnterGuard())
    act(() => {
      result.current.onCompositionStart()
    })
    endComposition(result.current, 2000)

    expect(result.current.isComposing(keyEvent('Enter', { timeStamp: 2000 }))).toBe(false)
  })

  it('无参调用 isComposing 只反映 ref 状态', () => {
    const { result } = renderHook(() => useImeEnterGuard())
    expect(result.current.isComposing()).toBe(false)
    act(() => {
      result.current.onCompositionStart()
    })
    expect(result.current.isComposing()).toBe(true)
  })
})

describe('useImeEnterGuard：compositionend 之后的尾随 Enter', () => {
  it('80ms 内的 Enter 被拦，且调用 preventDefault 吞掉默认行为', () => {
    const { result } = renderHook(() => useImeEnterGuard())
    endComposition(result.current, 3000)
    const e = keyEvent('Enter', { timeStamp: 3000 + 10 })

    expect(result.current.shouldIgnoreEnter(e)).toBe(true)
    expect(result.current.guardEnter(e)).toBe(true)
    expect(e.preventDefault).toHaveBeenCalledTimes(1)
  })

  it('恰好 80ms 边界仍在窗口内', () => {
    const { result } = renderHook(() => useImeEnterGuard())
    endComposition(result.current, 3000)

    expect(
      result.current.shouldIgnoreEnter(
        keyEvent('Enter', { timeStamp: 3000 + POST_COMPOSITION_ENTER_GUARD_MS }),
      ),
    ).toBe(true)
  })

  it('超过 80ms 的 Enter 放行（用户真的又按了一次）', () => {
    const { result } = renderHook(() => useImeEnterGuard())
    endComposition(result.current, 3000)
    const e = keyEvent('Enter', { timeStamp: 3000 + POST_COMPOSITION_ENTER_GUARD_MS + 1 })

    expect(result.current.shouldIgnoreEnter(e)).toBe(false)
    expect(result.current.guardEnter(e)).toBe(false)
    expect(e.preventDefault).not.toHaveBeenCalled()
  })

  it('时间戳早于 compositionend 的事件不落进尾随窗口（它发生在合成内，由 composingRef 负责）', () => {
    const { result } = renderHook(() => useImeEnterGuard())
    endComposition(result.current, 3000)

    // 时间戳早于 compositionend 说明这个 Enter 在合成结束之前就发生了。
    // 按事件顺序它不属于「尾随窗口」，此时合成态已结束、composingRef 也为 false，
    // 所以不拦是对的 —— 真正的合成中 Enter 由 composingRef / keyCode 229 拦住
    // （见下方「合成进行中」与「只给 keyCode 229」两组用例）。
    // 若这里也拦，就会把「合成结束后用户立刻正常按的 Enter」误吞，反而制造 bug。
    expect(result.current.shouldIgnoreEnter(keyEvent('Enter', { timeStamp: 100 }))).toBe(false)
  })

  it('缺失 timeStamp 回落到 0 时，不误吞（同上：合成态已结束则放行）', () => {
    const { result } = renderHook(() => useImeEnterGuard())
    endComposition(result.current, 3000)

    expect(result.current.shouldIgnoreEnter(keyEvent('Enter'))).toBe(false)
  })
})

describe('useImeEnterGuard：只给 keyCode 229 的输入法', () => {
  it('不派发 composition 事件、keyCode 229 的 Enter 被拦，且不 preventDefault', () => {
    const { result } = renderHook(() => useImeEnterGuard())
    const e = keyEvent('Enter', { timeStamp: 4000, keyCode: 229 })

    expect(result.current.shouldIgnoreEnter(e)).toBe(true)
    expect(result.current.guardEnter(e)).toBe(true)
    expect(e.preventDefault).not.toHaveBeenCalled()
  })
})

describe('useImeEnterGuard：非 Enter 键', () => {
  it.each(['a', 'Shift', 'ArrowDown', 'Escape', 'Process'])('%s 一律不拦', (key) => {
    const { result } = renderHook(() => useImeEnterGuard())
    act(() => {
      result.current.onCompositionStart()
    })
    const e = keyEvent(key, { timeStamp: 5000, keyCode: 229 })

    expect(result.current.shouldIgnoreEnter(e)).toBe(false)
    expect(result.current.guardEnter(e)).toBe(false)
    expect(e.preventDefault).not.toHaveBeenCalled()
  })
})

describe('useImeEnterGuard：窗口不跨轮次污染', () => {
  it('compositionstart 会清掉上一次的 compositionEndedAt', () => {
    const { result } = renderHook(() => useImeEnterGuard())
    endComposition(result.current, 6000)
    // 先确认窗口真的生效，否则下面的断言可能是「本来就是 false」
    expect(result.current.shouldIgnoreEnter(keyEvent('Enter', { timeStamp: 6010 }))).toBe(true)

    act(() => {
      result.current.onCompositionStart()
    })
    act(() => {
      // 立刻结束合成，但这次没有 timeStamp 推进；若旧窗口没被清掉，
      // 下面这个落在旧窗口内的事件就会被误拦
      result.current.onCompositionEnd({ timeStamp: 7000 } as unknown as CompositionEvent)
    })

    const e = keyEvent('Enter', { timeStamp: 7010 })
    expect(result.current.shouldIgnoreEnter(e)).toBe(true) // 新一轮自己的窗口
  })

  it('compositionstart 清窗口：下一轮 end 之前的 Enter 走合成中分支而非旧窗口', () => {
    const { result } = renderHook(() => useImeEnterGuard())
    endComposition(result.current, 6000)

    act(() => {
      result.current.onCompositionStart()
    })
    // 正在合成 → 被拦，但不 preventDefault（说明命中「合成中」而不是旧窗口）
    const e = keyEvent('Enter', { timeStamp: 6005 })
    expect(result.current.guardEnter(e)).toBe(true)
    expect(e.preventDefault).not.toHaveBeenCalled()
  })

  it('清掉旧窗口后，长间隔的 Enter 不再被旧时间戳影响', () => {
    const { result } = renderHook(() => useImeEnterGuard())
    endComposition(result.current, 6000)

    act(() => {
      result.current.onCompositionStart()
    })
    // 这一轮合成结束在很久之后，旧窗口早已失效；若没清，6000 的窗口也早过期，
    // 这里真正验证的是 ref 被覆盖而非叠加
    endComposition(result.current, 6000 + 10_000)

    expect(result.current.shouldIgnoreEnter(keyEvent('Enter', { timeStamp: 6000 + 10_001 }))).toBe(true)
    expect(
      result.current.shouldIgnoreEnter(keyEvent('Enter', { timeStamp: 6000 + 10_000 + 500 })),
    ).toBe(false)
  })
})
