// @vitest-environment jsdom
/**
 * useDocDirtyGuard：有未保存改动时，把「关文档 / 换文件」拦下来问一句。
 *
 * 三件事必须分开守：
 * 1. 不脏时**不许弹**（否则每次关文档都多一次确认，律师会学会盲点「放弃」）；
 * 2. 脏时动作必须**推迟**到用户选「放弃修改」，选「继续编辑」则一次都不许执行；
 * 3. 判断要读**点下去那一刻**的值——脏标记走 ref，靠 state 会漏拦第一次点击。
 */
import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useDocDirtyGuard } from './use-doc-dirty-guard'

describe('useDocDirtyGuard', () => {
  it('不脏时直接执行，不弹确认', () => {
    const { result } = renderHook(() => useDocDirtyGuard())
    const run = vi.fn()
    act(() => result.current.guard(run))
    expect(run).toHaveBeenCalledTimes(1)
    expect(result.current.pending).toBe(false)
  })

  it('脏时先挂起，选「放弃修改」才执行', () => {
    const { result } = renderHook(() => useDocDirtyGuard())
    act(() => result.current.markDirty(true))

    const run = vi.fn()
    act(() => result.current.guard(run))
    expect(run).not.toHaveBeenCalled()
    expect(result.current.pending).toBe(true)

    act(() => result.current.leave())
    expect(run).toHaveBeenCalledTimes(1)
    expect(result.current.pending).toBe(false)
  })

  it('选「继续编辑」：动作一次都不执行，脏标记保留', () => {
    const { result } = renderHook(() => useDocDirtyGuard())
    act(() => result.current.markDirty(true))

    const run = vi.fn()
    act(() => result.current.guard(run))
    act(() => result.current.stay())

    expect(run).not.toHaveBeenCalled()
    expect(result.current.pending).toBe(false)
    expect(result.current.dirty).toBe(true)
  })

  it('放弃修改后脏标记归零（下一次关文档不再重复问）', () => {
    const { result } = renderHook(() => useDocDirtyGuard())
    act(() => result.current.markDirty(true))
    act(() => result.current.guard(vi.fn()))
    act(() => result.current.leave())

    const next = vi.fn()
    act(() => result.current.guard(next))
    expect(next).toHaveBeenCalledTimes(1)
    expect(result.current.dirty).toBe(false)
  })
})
