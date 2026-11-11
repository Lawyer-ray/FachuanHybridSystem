// @vitest-environment jsdom
/**
 * useServiceItems：从合同文件夹读服务事项（jsdom + QueryClient）。
 *
 * 为什么不另建一张「服务事项」表：律师每天就在
 * `3-办案/2026.04.27-草拟付款确认书/` 里干活，事项名与日期都写在文件夹名上。
 *
 * 断言集中在三件容易错的事：
 * - **事项源目录**的自动识别（只认根层名字，不下探；认不出就 null，由页面让用户选）
 * - 交付状态看**有没有文件**而不是有没有日期（日期只说明计划过，文件才说明做完）
 * - 排序：有日期的按日期倒序在前，没日期的按名称序接在后面
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({ listFolderEntries: vi.fn() }))

vi.mock('../../api', () => apiMock)

import { useServiceItems } from './use-service-items'

function entries(folders: Array<{ name: string; subpath?: string; file_count?: number }>) {
  return {
    browsable: true,
    message: null,
    path_display: '/',
    subpath: '',
    parent_subpath: '',
    folders: folders.map((f) => ({ subpath: f.name, ...f })),
    files: [],
  }
}

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

function render(kind: 'case' | 'contract' = 'contract', ownerId: number | null = 9, sourceSubpath: string | null = null) {
  return renderHook(() => useServiceItems(kind, ownerId, { sourceSubpath }), { wrapper: wrapper() })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('事项源目录识别', () => {
  it('根层有「办案」目录时自动认作事项源', async () => {
    apiMock.listFolderEntries.mockImplementation((_k: string, _id: number, subpath: string) =>
      Promise.resolve(
        subpath === ''
          ? entries([{ name: '1-合同发票' }, { name: '3-办案' }])
          : entries([]),
      ),
    )
    const { result } = render()
    await waitFor(() => expect(result.current.sourceSubpath).toBe('3-办案'))
  })

  it('「法律服务」「日常事务」也认（同一语义的不同命名）', async () => {
    for (const name of ['2-法律服务', '3-日常事务']) {
      apiMock.listFolderEntries.mockImplementation((_k: string, _id: number, subpath: string) =>
        Promise.resolve(subpath === '' ? entries([{ name }]) : entries([])),
      )
      const { result } = render()
      await waitFor(() => expect(result.current.sourceSubpath).toBe(name))
    }
  })

  it('根层认不出时不静默扫全部子目录（sourceSubpath 为 null）', async () => {
    apiMock.listFolderEntries.mockResolvedValue(entries([{ name: '1-合同发票' }]))
    const { result } = render()
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.sourceSubpath).toBeNull()
    expect(result.current.items).toEqual([])
    // 只发了根层一次请求
    expect(apiMock.listFolderEntries).toHaveBeenCalledTimes(1)
  })

  it('手动指定优先于自动识别', async () => {
    apiMock.listFolderEntries.mockResolvedValue(entries([{ name: '3-办案' }]))
    const { result } = render('contract', 9, '5-自定义源')
    await waitFor(() => expect(result.current.sourceSubpath).toBe('5-自定义源'))
  })

  it('ownerId 为 null 时不发请求', async () => {
    const { result } = render('contract', null)
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(apiMock.listFolderEntries).not.toHaveBeenCalled()
  })
})

describe('事项解析与状态', () => {
  const SOURCE = '3-办案'

  function withItems(items: Array<{ name: string; file_count?: number }>) {
    apiMock.listFolderEntries.mockImplementation((_k: string, _id: number, subpath: string) =>
      Promise.resolve(subpath === '' ? entries([{ name: SOURCE }]) : entries(items)),
    )
  }

  it('从目录名解析日期与事项名', async () => {
    withItems([{ name: '2026.04.27-草拟付款确认书', file_count: 2 }])
    const { result } = render()
    await waitFor(() => expect(result.current.items).toHaveLength(1))
    expect(result.current.items[0]).toMatchObject({
      date: '2026-04-27',
      title: '草拟付款确认书',
      kind: '办案',
      fileCount: 2,
    })
  })

  it('有文件 = done（不管有没有日期）', async () => {
    withItems([{ name: '2026.04.27-已交文件', file_count: 1 }])
    const { result } = render()
    await waitFor(() => expect(result.current.items[0]?.status).toBe('done'))
  })

  it('无文件但有日期 = doing（计划过、还没产出）', async () => {
    withItems([{ name: '2026.04.27-进行中', file_count: 0 }])
    const { result } = render()
    await waitFor(() => expect(result.current.items[0]?.status).toBe('doing'))
  })

  it('无文件无日期 = todo', async () => {
    withItems([{ name: '没日期的事项', file_count: 0 }])
    const { result } = render()
    await waitFor(() => expect(result.current.items[0]?.status).toBe('todo'))
  })

  it('file_count 缺失按 0 处理', async () => {
    withItems([{ name: '2026.04.27-无计数' }])
    const { result } = render()
    await waitFor(() => expect(result.current.items[0]?.status).toBe('doing'))
  })

  it('排序：有日期的按日期倒序在前，无日期按名称序接后', async () => {
    withItems([
      { name: '2026.01.05-早的', file_count: 1 },
      { name: '2026.06.09-晚的', file_count: 1 },
      { name: '无日期 B', file_count: 0 },
      { name: '无日期 A', file_count: 0 },
    ])
    const { result } = render()
    await waitFor(() => expect(result.current.items).toHaveLength(4))
    expect(result.current.items.map((i) => i.title)).toEqual(['晚的', '早的', '无日期 A', '无日期 B'])
  })

  it('不再重复目录名（detail 恒 undefined）', async () => {
    withItems([{ name: '2026.06.09-租赁合同', file_count: 1 }])
    const { result } = render()
    await waitFor(() => expect(result.current.items).toHaveLength(1))
    expect(result.current.items[0]!.detail).toBeUndefined()
  })

  it('candidates 是根层目录（供页面「换个目录」下拉）', async () => {
    withItems([{ name: '2026.04.27-x', file_count: 1 }])
    const { result } = render()
    await waitFor(() => expect(result.current.items).toHaveLength(1))
    expect(result.current.candidates.map((c: { name: string }) => c.name)).toEqual([SOURCE])
  })
})
