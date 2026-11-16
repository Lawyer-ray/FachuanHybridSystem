// @vitest-environment jsdom
/**
 * `useToday` 的重新计算与引用稳定性（jsdom + fake timers）。
 *
 * 为什么不放在同目录的 use-today.test.ts：那个文件是 node 环境，只测
 * `msUntilMidnight` 这个纯函数；而本 hook 的价值全在**副作用时机**上，
 * 必须有 window/document 才能派 `visibilitychange`、排定时器。
 *
 * 三条契约，每条都有明确的用户可见后果：
 *
 * 1. **跨零点重算**。律师工作台常整夜不关，日期冻结在昨天的话，日历高亮、
 *    今日统计、今日到期红点会全部错一天。
 * 2. **日期没变时保持同一 Date 引用**。下游把 `today` 当 useMemo 依赖 / 查
 *    询参数；每次 recheck 都造新 Date 会让整棵树每秒重算（而 recheck 恰恰是
 *    定时器频繁触发的路径）。
 * 3. **`visibilitychange` 也重算**。标签页休眠时定时器会被节流甚至暂停，
 *    回前台不补一次的话，跨零点同样发现不了。
 *
 * 顺带守 `msUntilMidnight` 的「至少返回 1」：返回 0 会变成 0ms 定时器自旋，
 * 主线程被烧穿（那个纯函数测已覆盖「零点前 1ms」，这里只验 hook 不会因此空转）。
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useToday } from './use-today'

/** 把「现在」钉在某个本地时刻（hook 内部用 `new Date()`，只能改系统时钟） */
function setNow(y: number, m: number, d: number, h = 9, min = 0) {
  vi.setSystemTime(new Date(y, m, d, h, min, 0, 0))
}

function midnightOf(y: number, m: number, d: number) {
  return new Date(y, m, d, 0, 0, 0, 0).getTime()
}

afterEach(() => {
  vi.useRealTimers()
})

beforeEach(() => {
  vi.useFakeTimers()
})

describe('useToday：跨零点重算', () => {
  it('初始值就是今天零点（不是当前时刻）', () => {
    setNow(2026, 4, 12, 15, 30)
    const { result } = renderHook(() => useToday())
    expect(result.current.getTime()).toBe(midnightOf(2026, 4, 12))
  })

  it('定时器走到次日零点后，日期跟着推进（整夜不关的工作台不能停在昨天）', () => {
    setNow(2026, 4, 12, 23, 59)
    const { result } = renderHook(() => useToday())
    expect(result.current.getTime()).toBe(midnightOf(2026, 4, 12))

    // 排的是「到下一个零点的精确毫秒数」，推进 1 分钟就跨天
    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    expect(result.current.getTime()).toBe(midnightOf(2026, 4, 13))
  })

  it('日期没变时保持同一 Date 引用（下游 useMemo 不能无谓失效）', () => {
    setNow(2026, 4, 12, 9, 0)
    const { result } = renderHook(() => useToday())
    const first = result.current

    // 回前台 / 定时器重排都会触发 recheck；这里模拟同一天内的再次触发
    act(() => {
      vi.setSystemTime(new Date(2026, 4, 12, 18, 0, 0, 0))
      document.dispatchEvent(new Event('visibilitychange'))
    })

    // 新造 Date 的话下游所有 useMemo/查询参数都会失效，整页重算
    expect(result.current).toBe(first)
  })

  it('visibilitychange 在跨天后立刻补一次（休眠时定时器可能被暂停）', () => {
    setNow(2026, 4, 12, 9, 0)
    const { result } = renderHook(() => useToday())
    const before = result.current.getTime()

    act(() => {
      // 标签页休眠跨过了零点：定时器没跑，只能靠回前台补
      vi.setSystemTime(new Date(2026, 4, 13, 8, 0, 0, 0))
      document.dispatchEvent(new Event('visibilitychange'))
    })

    expect(before).toBe(midnightOf(2026, 4, 12))
    expect(result.current.getTime()).toBe(midnightOf(2026, 4, 13))
  })

  it('卸载时清定时器与监听（否则组件走了还在 setState）', () => {
    setNow(2026, 4, 12, 9, 0)
    const removeSpy = vi.spyOn(document, 'removeEventListener')
    const { unmount } = renderHook(() => useToday())
    unmount()
    expect(removeSpy).toHaveBeenCalledWith('visibilitychange', expect.any(Function))
    expect(vi.getTimerCount()).toBe(0)
    removeSpy.mockRestore()
  })
})
