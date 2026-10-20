// @vitest-environment jsdom
/**
 * usePollSession 会话守卫单测（jsdom）。
 *
 * 重点覆盖 StrictMode：开发态 React 对新挂载的组件把 effect 跑成
 * 「setup → cleanup → setup」。若 cleanup 的「卸载即失效」不可逆，挂载 effect 里
 * 签发的 lease 会被这次假卸载永久打成 stale——消费方若用 ref 防重（同一文件不
 * 二次提交），就再没有机会签发新 lease，在飞的请求返回后被静默吞掉。
 */
import { useEffect, useRef } from 'react'
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { usePollSession, type PollLease } from './use-poll-session'

/**
 * 必须用 RTL 的 reactStrictMode 选项把 <StrictMode> 放在最顶层：React 只对带
 * PlacementDEV 的最顶层新挂载 fiber 做双调用、且要求它已处于 StrictMode 内；
 * 若用函数组件 wrapper 包一层 <StrictMode>，顶层新挂载的是 wrapper 本身，
 * React 会跳过整棵子树的双调用（实测 setup 只跑 1 次），测试会假绿。
 */
const STRICT = { reactStrictMode: true } as const

/**
 * 模拟 RecognizeDialog 的用法：挂载 effect 里签发一次 lease，ref 防重，
 * StrictMode 的第二次 setup 不会再签发。
 */
function useLeaseOnMount() {
  const pollSession = usePollSession()
  const lease = useRef<PollLease | null>(null)
  useEffect(() => {
    if (lease.current) return
    lease.current = pollSession.begin()
  }, [pollSession])
  return { lease, pollSession }
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('usePollSession × StrictMode', () => {
  it('挂载 effect 签发的 lease 经 StrictMode 的 cleanup→setup 双调用后仍然有效', () => {
    const { result } = renderHook(() => useLeaseOnMount(), STRICT)
    expect(result.current.lease.current).not.toBeNull()
    expect(result.current.lease.current!.isStale()).toBe(false)
  })

  it('双调用后签发的 lease 仍能正常 sleep 并按时醒来', async () => {
    const { result } = renderHook(() => useLeaseOnMount(), STRICT)
    const lease = result.current.lease.current!
    let woke = false
    void lease.sleep(1_000).then(() => {
      woke = true
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(999)
    })
    expect(woke).toBe(false)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    expect(woke).toBe(true)
    expect(lease.isStale()).toBe(false)
  })

  it('真实卸载后 lease 失效，挂着的 sleep 立即放行', async () => {
    const { result, unmount } = renderHook(() => useLeaseOnMount(), STRICT)
    const lease = result.current.lease.current!
    let woke = false
    void lease.sleep(60_000).then(() => {
      woke = true
    })
    unmount()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(lease.isStale()).toBe(true)
    expect(woke).toBe(true)
  })
})

describe('usePollSession 会话语义', () => {
  it('begin() 让旧 lease 失效并唤醒其挂着的 sleep；新 lease 有效', async () => {
    const { result } = renderHook(() => usePollSession())
    const old = result.current.begin()
    let woke = false
    void old.sleep(60_000).then(() => {
      woke = true
    })
    const fresh = result.current.begin()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(old.isStale()).toBe(true)
    expect(woke).toBe(true)
    expect(fresh.isStale()).toBe(false)
  })

  it('invalidate() 只失效当前会话，不签发新会话', async () => {
    const { result } = renderHook(() => usePollSession())
    const lease = result.current.begin()
    let woke = false
    void lease.sleep(60_000).then(() => {
      woke = true
    })
    result.current.invalidate()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(lease.isStale()).toBe(true)
    expect(woke).toBe(true)
  })

  it('已失效 lease 的 sleep 立即放行，不再占用计时器', async () => {
    const { result } = renderHook(() => usePollSession())
    const lease = result.current.begin()
    result.current.invalidate()
    let woke = false
    void lease.sleep(60_000).then(() => {
      woke = true
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(woke).toBe(true)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('返回对象引用在重渲染间稳定（消费方 useCallback 依赖不随渲染漂移）', () => {
    const { result, rerender } = renderHook(() => usePollSession())
    const first = result.current
    rerender()
    expect(result.current).toBe(first)
  })
})
