// @vitest-environment jsdom
/**
 * useMediaQuery 单测（jsdom）。
 *
 * jsdom 未实现 window.matchMedia，用可控行为的替身（matches 可变 +
 * change 监听登记表）驱动：初始值、跨断点 change 事件更新、
 * 卸载/换 query 时的订阅清理。
 */
import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useMediaQuery } from './use-media'

type ChangeListener = (e: { matches: boolean }) => void

function installMatchMedia() {
  const state = new Map<string, boolean>()
  const listeners = new Map<string, Set<ChangeListener>>()
  const matchMedia = vi.fn((q: string) => ({
    get matches() {
      return state.get(q) ?? false
    },
    addEventListener: (_kind: string, cb: ChangeListener) => {
      if (!listeners.has(q)) listeners.set(q, new Set())
      listeners.get(q)!.add(cb)
    },
    removeEventListener: (_kind: string, cb: ChangeListener) => {
      listeners.get(q)?.delete(cb)
    },
  }))
  window.matchMedia = matchMedia as unknown as typeof window.matchMedia
  return {
    matchMedia,
    set(q: string, matches: boolean) {
      state.set(q, matches)
      for (const cb of listeners.get(q) ?? []) cb({ matches })
    },
    listenerCount: (q: string) => listeners.get(q)?.size ?? 0,
  }
}

describe('useMediaQuery', () => {
  it('初始值取 matchMedia().matches（true / false）', () => {
    const mq = installMatchMedia()
    mq.set('(max-width: 760px)', true)
    const { result } = renderHook(() => useMediaQuery('(max-width: 760px)'))
    expect(result.current).toBe(true)

    const { result: r2 } = renderHook(() => useMediaQuery('(min-width: 1100px)'))
    expect(r2.current).toBe(false)
  })

  it('change 事件跨断点时更新', () => {
    const mq = installMatchMedia()
    const { result } = renderHook(() => useMediaQuery('(max-width: 760px)'))
    expect(result.current).toBe(false)

    act(() => mq.set('(max-width: 760px)', true))
    expect(result.current).toBe(true)

    act(() => mq.set('(max-width: 760px)', false))
    expect(result.current).toBe(false)
  })

  it('卸载后移除监听（断点再变不影响已卸载 hook）', () => {
    const mq = installMatchMedia()
    const { result, unmount } = renderHook(() => useMediaQuery('(max-width: 760px)'))
    expect(mq.listenerCount('(max-width: 760px)')).toBe(1) // 只有 effect 里的订阅
    unmount()
    expect(mq.listenerCount('(max-width: 760px)')).toBe(0)

    act(() => mq.set('(max-width: 760px)', true))
    expect(result.current).toBe(false) // 已卸载，不再更新
  })

  it('query 变化：旧订阅拆掉、按新 query 重订阅（match 以 change 事件为准刷新）', () => {
    const mq = installMatchMedia()
    const { result, rerender } = renderHook(({ q }) => useMediaQuery(q), {
      initialProps: { q: '(max-width: 760px)' },
    })
    act(() => mq.set('(max-width: 760px)', true))
    expect(result.current).toBe(true)

    rerender({ q: '(min-width: 1100px)' })
    expect(mq.listenerCount('(max-width: 760px)')).toBe(0)
    // 状态不因换 query 重算（沿用旧值），新 query 的 change 事件才刷新
    expect(result.current).toBe(true)
    act(() => mq.set('(min-width: 1100px)', false))
    expect(result.current).toBe(false)
    act(() => mq.set('(min-width: 1100px)', true))
    expect(result.current).toBe(true)
  })
})
