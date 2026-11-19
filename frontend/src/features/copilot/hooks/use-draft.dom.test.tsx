// @vitest-environment jsdom
/**
 * useDraft 测试（jsdom + localStorage）。
 *
 * 不变量：
 * - 打开会话时回填该会话的草稿（刷新不丢）
 * - 输入去抖后才落盘（不是每次按键写同步 IO）
 * - 切会话：先把旧会话的草稿写进**旧 key**，再载入新会话的草稿
 * - 清空（发送后 setText('')）等于删 key
 * - 去抖窗口内卸载也要补写最后一笔
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useDraft } from './use-draft'

const WRITE_DEBOUNCE_MS = 300

beforeEach(() => {
  localStorage.clear()
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useDraft', () => {
  it('初始回填该会话已存在的草稿', () => {
    localStorage.setItem('copilot:draft:s-1', '上次写到一半的诉求')
    const { result } = renderHook(() => useDraft('s-1'))
    expect(result.current[0]).toBe('上次写到一半的诉求')
  })

  it('没有会话时用 new 键（首条消息也不丢）', () => {
    localStorage.setItem('copilot:draft:new', '还没建会话')
    const { result } = renderHook(() => useDraft(null))
    expect(result.current[0]).toBe('还没建会话')
  })

  it('输入去抖后落盘', () => {
    const { result } = renderHook(() => useDraft('s-1'))
    act(() => result.current[1]('新的草稿'))
    // 去抖窗口内还没写
    expect(localStorage.getItem('copilot:draft:s-1')).toBeNull()
    act(() => vi.advanceTimersByTime(WRITE_DEBOUNCE_MS))
    expect(localStorage.getItem('copilot:draft:s-1')).toBe('新的草稿')
  })

  it('清空等于删 key（不留下空草稿）', () => {
    localStorage.setItem('copilot:draft:s-1', '旧的')
    const { result } = renderHook(() => useDraft('s-1'))
    act(() => result.current[1](''))
    act(() => vi.advanceTimersByTime(WRITE_DEBOUNCE_MS))
    expect(localStorage.getItem('copilot:draft:s-1')).toBeNull()
  })

  it('切会话：旧草稿写旧 key，新会话回填自己的草稿', () => {
    localStorage.setItem('copilot:draft:s-2', 'B 会话的草稿')
    const { result, rerender } = renderHook(({ id }: { id: string | null }) => useDraft(id), {
      initialProps: { id: 's-1' as string | null },
    })
    act(() => result.current[1]('A 会话写到一半'))

    rerender({ id: 's-2' })

    expect(localStorage.getItem('copilot:draft:s-1')).toBe('A 会话写到一半')
    expect(result.current[0]).toBe('B 会话的草稿')
  })

  it('去抖窗口内卸载：最后一笔也补写', () => {
    const { result, unmount } = renderHook(() => useDraft('s-1'))
    act(() => result.current[1]('来不及等去抖'))
    unmount()
    expect(localStorage.getItem('copilot:draft:s-1')).toBe('来不及等去抖')
  })
})
