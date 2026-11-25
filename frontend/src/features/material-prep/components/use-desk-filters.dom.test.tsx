// @vitest-environment jsdom
/**
 * `useDeskFilters` 的收件箱档位语义（jsdom）。
 *
 * 这个 hook 是「首屏落在哪一档 + 谁有权改它」的唯一真源，两件事只有在这里
 * 才测得到（纯模块测不到 hook 的两个 setter 分工）：
 *
 * 1. 首次进入 = 邮箱；
 * 2. `setSource`（用户点药丸）会**记住**选择；
 * 3. `overrideSource`（深链接为找目标消息而放开筛选）**不记**偏好——
 *    记了就等于把「进来默认邮箱」废掉，这次会话里永远被钉在「全部」。
 *
 * 同时锁住「未读数取当前档位」：档位变了，取数参数跟着变，未读数才不会拿
 * 一档的数字去配另一档的列表。
 */
import { act, renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const hookMock = vi.hoisted(() => ({
  useInboxList: vi.fn((_params: unknown) => ({ data: [], isLoading: false, error: null, refetch: vi.fn() })),
}))

vi.mock('../inbox/hooks/use-inbox', () => ({ useInboxList: hookMock.useInboxList }))

import { resolveInitialInboxSource, resetInboxSourcePreference } from '../inbox/default-source'
import { useDeskFilters } from './use-desk-filters'

function wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter initialEntries={['/material-prep']}>{children}</MemoryRouter>
}

beforeEach(() => {
  hookMock.useInboxList.mockClear()
  resetInboxSourcePreference()
})

describe('useDeskFilters：收件箱档位', () => {
  it('首次进入是邮箱，取数也按邮箱拿', () => {
    const { result, unmount } = renderHook(() => useDeskFilters(), { wrapper })
    expect(result.current.source).toBe('imap')
    expect(hookMock.useInboxList).toHaveBeenCalledWith({ source: 'imap', search: '' })
    unmount()
  })

  it('用户点药丸：状态与偏好一起更新（离开再回来仍在那一档）', () => {
    const { result, unmount } = renderHook(() => useDeskFilters(), { wrapper })
    act(() => result.current.setSource('court_inbox'))
    expect(result.current.source).toBe('court_inbox')
    expect(resolveInitialInboxSource()).toBe('court_inbox')
    unmount()
  })

  it('程序改档（深链接放开筛选）不写偏好', () => {
    const { result, unmount } = renderHook(() => useDeskFilters(), { wrapper })
    act(() => result.current.overrideSource('all'))
    expect(result.current.source).toBe('all')
    // 关键断言：偏好仍是「邮箱」——否则这次会话里每次回收件箱都被钉在「全部」
    expect(resolveInitialInboxSource()).toBe('imap')
    unmount()
  })

  it('程序改档之后用户自己点一次，才真正记住', () => {
    const { result, unmount } = renderHook(() => useDeskFilters(), { wrapper })
    act(() => result.current.overrideSource('all'))
    act(() => result.current.setSource('court_sms'))
    expect(resolveInitialInboxSource()).toBe('court_sms')
    unmount()
  })
})
