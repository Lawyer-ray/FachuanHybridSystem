// @vitest-environment jsdom
/**
 * hooks/use-copy-feedback 单测（jsdom）。
 *
 * 用假时钟验证 copied 的翻转与自动复位，并锁住两条清理契约：
 * 1) 重复复制时旧定时器必须清掉（否则第二次的「已复制」会被上一次的计时提前打回）；
 * 2) 卸载时清定时器（否则卸载后 setState 告警）。
 * 复制本身走 lib/clipboard 的 copyText——这里按路径返回值而不去碰 navigator，
 * 保证「必须走带 execCommand 兜底的 copyText」这条不被绕过（vi.mock 掉它就说明没走）。
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const copyTextMock = vi.hoisted(() => vi.fn())

vi.mock('@/lib/clipboard', () => ({ copyText: copyTextMock }))

import { useCopyFeedback } from './use-copy-feedback'

beforeEach(() => {
  vi.useFakeTimers()
  copyTextMock.mockReset()
  copyTextMock.mockResolvedValue(true)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useCopyFeedback', () => {
  it('复制成功 → copied 置 true，resetMs 后自动复位', async () => {
    const { result, unmount } = renderHook(() => useCopyFeedback({ resetMs: 1500 }))
    expect(result.current.copied).toBe(false)

    await act(async () => {
      await expect(result.current.copy('案件摘要')).resolves.toBe(true)
    })
    expect(copyTextMock).toHaveBeenCalledWith('案件摘要')
    expect(result.current.copied).toBe(true)

    act(() => {
      vi.advanceTimersByTime(1499)
    })
    expect(result.current.copied).toBe(true)

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(result.current.copied).toBe(false)
    unmount()
  })

  it('默认 2000ms 后复位', async () => {
    const { result, unmount } = renderHook(() => useCopyFeedback())
    await act(async () => {
      await result.current.copy('x')
    })
    act(() => {
      vi.advanceTimersByTime(1999)
    })
    expect(result.current.copied).toBe(true)
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(result.current.copied).toBe(false)
    unmount()
  })

  it('复制失败 → 回 false 且 copied 保持 false（不误导用户以为已复制）', async () => {
    copyTextMock.mockResolvedValue(false)
    const { result, unmount } = renderHook(() => useCopyFeedback())
    await act(async () => {
      await expect(result.current.copy('x')).resolves.toBe(false)
    })
    expect(result.current.copied).toBe(false)
    unmount()
  })

  it('重复复制重置计时：第二次不会因上一次的旧定时器提前复位', async () => {
    const { result, unmount } = renderHook(() => useCopyFeedback({ resetMs: 1000 }))
    await act(async () => {
      await result.current.copy('第一次')
    })
    act(() => {
      vi.advanceTimersByTime(800)
    })
    await act(async () => {
      await result.current.copy('第二次')
    })
    // 距第一次 1000ms（第一次的定时器原本到点），复制态应仍在
    act(() => {
      vi.advanceTimersByTime(200)
    })
    expect(result.current.copied).toBe(true)
    // 距第二次满 1000ms 才复位
    act(() => {
      vi.advanceTimersByTime(800)
    })
    expect(result.current.copied).toBe(false)
    unmount()
  })

  it('卸载清定时器：残留计时不会在卸载后触发 setState', async () => {
    const { result, unmount } = renderHook(() => useCopyFeedback({ resetMs: 1000 }))
    await act(async () => {
      await result.current.copy('x')
    })
    expect(vi.getTimerCount()).toBe(1)
    unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('复制进行中卸载：飞行中的结果不再写状态', async () => {
    let release: (v: boolean) => void = () => {}
    copyTextMock.mockImplementation(() => new Promise<boolean>((res) => (release = res)))
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const { result, unmount } = renderHook(() => useCopyFeedback())
    const pending = result.current.copy('x')
    unmount()
    await act(async () => {
      release(true)
      await expect(pending).resolves.toBe(true)
    })
    // 卸载后不得再起复位定时器，也不得有 React 的 setState-on-unmounted 告警
    expect(vi.getTimerCount()).toBe(0)
    expect(errorSpy).not.toHaveBeenCalled()
    errorSpy.mockRestore()
  })
})
