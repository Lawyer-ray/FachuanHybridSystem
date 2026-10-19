// @vitest-environment jsdom
/**
 * useTypeaheadSearch 单测（jsdom）。
 * 覆盖五处收敛来源的关键行为：防抖后才请求、空关键词不发（minLength）、
 * signal 透传、附加 enabled 条件。mock 只打检索函数本身，react-query 与防抖 hook
 * 保持真实；防抖毫秒压到 30ms 走真实计时器（快且不与 react-query 内部计时冲突）。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useTypeaheadSearch } from './use-typeahead-search'

const searchMock = vi.fn()

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

beforeEach(() => {
  searchMock.mockReset()
})

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

interface Opts {
  minLength?: number
  enabled?: boolean
  debounceMs?: number
}

function renderSearch(opts: Opts = {}) {
  return renderHook(
    () =>
      useTypeaheadSearch<string[]>({
        queryKey: (kw) => ['test-search', kw],
        queryFn: ({ keyword, signal }) => searchMock(keyword, signal),
        debounceMs: opts.debounceMs ?? 30,
        ...opts,
      }),
    { wrapper },
  )
}

describe('useTypeaheadSearch', () => {
  it('首帧（空关键词）按 minLength 决定是否请求：默认不发', async () => {
    searchMock.mockResolvedValue([])
    const { result } = renderSearch()
    expect(result.current.keyword).toBe('')
    await act(async () => {
      await sleep(80)
    })
    expect(searchMock).not.toHaveBeenCalled()
  })

  it('minLength 0：挂载即以空关键词拉初始列表（court-sms 口径）', async () => {
    searchMock.mockResolvedValue(['初始'])
    const { result } = renderSearch({ minLength: 0 })
    await waitFor(() => expect(result.current.data).toEqual(['初始']))
    expect(searchMock).toHaveBeenCalledWith('', expect.any(AbortSignal))
  })

  it('输入停满防抖毫秒才请求，且关键词先 trim', async () => {
    searchMock.mockResolvedValue(['命中'])
    const { result } = renderSearch({ debounceMs: 60 })
    act(() => result.current.setKeyword('  张三 '))
    // 防抖窗口内不发
    await act(async () => {
      await sleep(30)
    })
    expect(searchMock).not.toHaveBeenCalled()
    await waitFor(() => expect(result.current.data).toEqual(['命中']))
    expect(searchMock).toHaveBeenCalledWith('张三', expect.any(AbortSignal))
    // raw 值保留原样（喂输入框），防抖值是 trim 后的
    expect(result.current.keyword).toBe('  张三 ')
    expect(result.current.debounced).toBe('张三')
  })

  it('minLength 2：单字符不发，两字符才发（文书识别口径）', async () => {
    searchMock.mockResolvedValue([])
    const { result } = renderSearch({ minLength: 2 })
    act(() => result.current.setKeyword('张'))
    await act(async () => {
      await sleep(80)
    })
    expect(searchMock).not.toHaveBeenCalled()
    act(() => result.current.setKeyword('张三'))
    await waitFor(() => expect(searchMock).toHaveBeenCalledExactlyOnceWith('张三', expect.any(AbortSignal)))
  })

  it('附加 enabled=false 时有关键词也不发，翻 true 后恢复（弹窗开关口径）', async () => {
    searchMock.mockResolvedValue(['x'])
    const { result, rerender } = renderHook(
      ({ enabled }: { enabled?: boolean }) =>
        useTypeaheadSearch<string[]>({
          queryKey: (kw) => ['test-search', kw],
          queryFn: ({ keyword, signal }) => searchMock(keyword, signal),
          enabled,
          debounceMs: 30,
        }),
      { wrapper, initialProps: { enabled: false } },
    )
    act(() => result.current.setKeyword('abc'))
    await act(async () => {
      await sleep(80)
    })
    expect(searchMock).not.toHaveBeenCalled()
    rerender({ enabled: true })
    await waitFor(() => expect(searchMock).toHaveBeenCalledExactlyOnceWith('abc', expect.any(AbortSignal)))
  })
})
