// @vitest-environment jsdom
/**
 * useSpecialPhases：专项阶段的数据装配（jsdom + QueryClient）。
 *
 * 被测契约：
 * - 阶段来自 `GET contracts/{id}/stages`；为空时用根目录里「序号-阶段名」兜底
 * - 交付物来自合同文件夹：每级阶段一个 folder-entries 请求，目录名由 `folderNameOf` 派生
 * - 实际文件顶掉同名计划项（避免「计划 3 份、实交 1 份」出现两行同名）
 * - 保存：先落本地再试后端；后端返回的树不带 `open` 时以本地展开态为准
 * - 展开/折叠只落本地，**不发 PUT**（曾经每点一下行就 PUT 一次）
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  getContractStages: vi.fn(),
  putContractStages: vi.fn(),
  listFolderEntries: vi.fn(),
}))

vi.mock('../../api', () => apiMock)
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { toast } from 'sonner'

import { useSpecialPhases } from './use-special-phases'

function folderEntries(folders: Array<{ name: string; file_count?: number }> = [], files: Array<{ name: string; subpath: string }> = []) {
  return {
    browsable: true,
    message: null,
    path_display: '/',
    subpath: '',
    parent_subpath: '',
    folders: folders.map((f) => ({ subpath: f.name, ...f })),
    files: files.map((f) => ({ size: 10, modified_at: '2026-10-20T10:00:00', ...f })),
  }
}

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

function render(kind: 'case' | 'contract' = 'contract', ownerId: number | null = 9) {
  return renderHook(() => useSpecialPhases(kind, ownerId), { wrapper: wrapper() })
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.getContractStages.mockResolvedValue([])
  apiMock.listFolderEntries.mockResolvedValue(folderEntries())
})

describe('阶段来源', () => {
  it('ownerId 为 null 时不发任何请求（页面还没拿到 id）', async () => {
    const { result } = render('contract', null)
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(apiMock.getContractStages).not.toHaveBeenCalled()
    expect(apiMock.listFolderEntries).not.toHaveBeenCalled()
    expect(result.current.tree).toEqual([])
  })

  it('结构化阶段为空、但根目录认得出阶段目录时用目录兜底', async () => {
    apiMock.listFolderEntries.mockImplementation((_kind: string, _id: number, subpath: string) => {
      if (subpath === '') {
        return Promise.resolve(folderEntries([{ name: '1-尽职调查', file_count: 2 }, { name: '2-方案设计', file_count: 0 }]))
      }
      return Promise.resolve(folderEntries())
    })
    const { result } = render()
    await waitFor(() => expect(result.current.tree.map((n) => n.name)).toEqual(['尽职调查', '方案设计']))
    // 目录兜底只给**结构**（名称/目录序号），状态由 derivePhaseStates 从交付物重算：
    // 本用例两个阶段目录都没读到文件，所以依次是「进行中」「未开始」。
    expect(result.current.tree.map((n) => n.state)).toEqual(['doing', 'todo'])
    // 展开态：进行中的那一级默认展开（phaseFromFolder 的口径）
    expect(result.current.tree.map((n) => n.open)).toEqual([false, true])
  })

  it('结构化阶段非空时以它为准（不再用目录兜底）', async () => {
    apiMock.getContractStages.mockResolvedValue([
      { key: 'ph_1', name: '结构化阶段', acceptance: '', open: false, startDate: '', folders: [], deliverables: [] },
    ])
    const { result } = render()
    await waitFor(() => expect(result.current.tree.map((n) => n.name)).toEqual(['结构化阶段']))
  })

  it('读阶段失败时 stagesError 有文案，树为空（不白屏）', async () => {
    apiMock.getContractStages.mockRejectedValue(new Error('404'))
    const { result } = render()
    await waitFor(() => expect(result.current.stagesError).toBeTruthy())
    expect(result.current.tree).toEqual([])
  })
})

describe('交付物：按目录名读文件', () => {
  it('每级阶段一个 folder-entries 请求，目录名 = <编号>-<阶段名>', async () => {
    apiMock.getContractStages.mockResolvedValue([
      { key: 'ph_1', name: '尽职调查', acceptance: '', open: true, startDate: '', folders: [], deliverables: [] },
      {
        key: 'ph_2',
        name: '方案设计',
        acceptance: '',
        open: false,
        startDate: '',
        folders: [{ key: 'ph_2_1', name: '职工安置', acceptance: '', open: false, startDate: '', folders: [], deliverables: [] }],
        deliverables: [],
      },
    ])
    render()
    await waitFor(() => {
      const paths = apiMock.listFolderEntries.mock.calls.map((c) => c[2])
      expect(paths).toContain('')
      expect(paths).toContain('1-尽职调查')
      expect(paths).toContain('2-方案设计')
      expect(paths).toContain('2.1-职工安置')
    })
  })

  it('阶段目录里的文件进交付物，且顶掉同名计划项', async () => {
    apiMock.getContractStages.mockResolvedValue([
      {
        key: 'ph_1',
        name: '尽职调查',
        acceptance: '',
        open: true,
        startDate: '',
        folders: [],
        deliverables: [
          { id: 'plan', date: '', name: '《尽调报告》', version: '', state: 'todo', planned: true },
          { id: 'keep', date: '', name: '《另案报告》', version: '', state: 'todo', planned: true },
        ],
      },
    ])
    apiMock.listFolderEntries.mockImplementation((_kind: string, _id: number, subpath: string) =>
      Promise.resolve(
        subpath === '1-尽职调查'
          ? folderEntries([], [{ name: '《尽调报告》.pdf', subpath: '1-尽职调查/《尽调报告》.pdf' }])
          : folderEntries(),
      ),
    )
    const { result } = render()
    await waitFor(() => expect(result.current.tree[0]?.deliverables).toHaveLength(2))
    const names = result.current.tree[0]!.deliverables.map((d) => d.name)
    // 同名计划项被真实文件顶掉，未撞名的计划项保留（书名号在 splitVersion 里保留）
    expect(names).toContain('《另案报告》')
    const real = result.current.tree[0]!.deliverables.find((d) => d.id === 'file:1-尽职调查/《尽调报告》.pdf')
    expect(real).toMatchObject({ planned: false, subpath: '1-尽职调查/《尽调报告》.pdf' })
    expect(result.current.tree[0]!.deliverables.some((d) => d.id === 'plan')).toBe(false)
    expect(result.current.tree[0]!.deliverables.some((d) => d.id === 'keep')).toBe(true)
  })
})

describe('保存阶段树', () => {
  const subtree = (open: boolean) => [
    { key: 'ph_1', name: '尽职调查', acceptance: '', open, startDate: '', folders: [], deliverables: [] },
  ]

  it('ownerId 为 null 时只落本地，不发 PUT', async () => {
    const { result } = render('contract', null)
    await act(async () => {
      await result.current.saveStages(subtree(true))
    })
    expect(apiMock.putContractStages).not.toHaveBeenCalled()
    expect(result.current.tree[0]?.open).toBe(true)
  })

  it('成功后 toast 条数、并采用后端返回的树', async () => {
    apiMock.putContractStages.mockResolvedValue(subtree(false).map((n) => ({ ...n, name: '后端改名' })))
    const { result } = render()
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    await act(async () => {
      await result.current.saveStages(subtree(true))
    })
    expect(apiMock.putContractStages).toHaveBeenCalledWith(9, expect.any(Array))
    expect(toast.success).toHaveBeenCalledWith('阶段已保存（1 个）')
    expect(result.current.tree[0]?.name).toBe('后端改名')
  })

  it('后端返回不带 open 时以本地展开态为准（保存不缩回展开行）', async () => {
    apiMock.putContractStages.mockResolvedValue(
      subtree(false).map(({ open: _open, ...rest }) => ({ ...rest, open: false })),
    )
    const { result } = render()
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    await act(async () => {
      await result.current.saveStages(subtree(true))
    })
    // keepOpenState 按 key 把本地的 open=true 搬回服务端最新树
    expect(result.current.tree[0]?.open).toBe(true)
  })

  it('后端返回空树时用本地派生树（端点未上线不丢改动）', async () => {
    apiMock.putContractStages.mockResolvedValue([])
    const { result } = render()
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    await act(async () => {
      await result.current.saveStages(subtree(true))
    })
    expect(toast.success).toHaveBeenCalledWith('阶段已保存（1 个）')
    expect(result.current.tree[0]?.name).toBe('尽职调查')
  })

  it('写回失败时提示「只保存在本页」，并保留本地改动', async () => {
    apiMock.putContractStages.mockRejectedValue(new Error('503'))
    const { result } = render()
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    await act(async () => {
      await result.current.saveStages(subtree(true).map((n) => ({ ...n, name: '本地改名' })))
    })
    expect(toast.error).toHaveBeenCalledWith(
      '阶段只保存在本页，未写入服务器',
      expect.objectContaining({ description: expect.any(String) }),
    )
    expect(result.current.tree[0]?.name).toBe('本地改名')
    expect(result.current.saving).toBe(false)
  })
})

describe('展开/折叠只落本地', () => {
  it('setTreeLocal 只落本地，不发 PUT', async () => {
    const { result } = render()
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    act(() => {
      result.current.setTreeLocal([
        { key: 'ph_1', name: '尽职调查', acceptance: '', open: true, startDate: '', folders: [], deliverables: [] },
      ])
    })
    expect(result.current.tree[0]?.open).toBe(true)
    expect(apiMock.putContractStages).not.toHaveBeenCalled()
  })

  it('refetch 重拉阶段与根目录', async () => {
    const { result } = render()
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    const stagesBefore = apiMock.getContractStages.mock.calls.length
    act(() => {
      result.current.refetch()
    })
    await waitFor(() => expect(apiMock.getContractStages.mock.calls.length).toBeGreaterThan(stagesBefore))
  })
})
