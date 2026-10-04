// @vitest-environment jsdom
/**
 * material-prep 收件箱 hooks 单测（jsdom）。
 *
 * mock 只打 api 层（../api 的列表 / 上传 / 打标 / 删除 / 重命名），
 * 覆盖：useMaterialPacks 的查询配置（staleTime / 禁 focus 重拉）与数据透传、
 * 四个变更 hook 的参数下推与成功后 PACKS_KEY 失效、失败路径不失效。
 */
import { type ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>()
  return {
    ...actual,
    listMaterialPacks: vi.fn(),
    uploadPack: vi.fn(),
    setPackStatusRemote: vi.fn(),
    deletePack: vi.fn(),
    renamePack: vi.fn(),
  }
})

import { deletePack, listMaterialPacks, renamePack, setPackStatusRemote, uploadPack } from '../api'
import type { InboxMessage, InboxMessageDetail } from '../types'

import { PACKS_KEY, useCreatePack, useDeletePack, useJudgePack, useMaterialPacks, useRenamePack } from './use-inbox'

const listMock = vi.mocked(listMaterialPacks)
const uploadMock = vi.mocked(uploadPack)
const setStatusMock = vi.mocked(setPackStatusRemote)
const deleteMock = vi.mocked(deletePack)
const renameMock = vi.mocked(renamePack)

function makePack(id: number, subject: string): InboxMessage {
  return {
    id,
    source_name: '手动上传',
    source_type: 'manual_upload',
    subject,
    sender: '',
    recipient: '',
    received_at: '2026-10-01 10:00:00',
    has_attachments: true,
    attachment_count: 1,
    uploaded_by_id: null,
    uploaded_by_name: '',
    created_at: '2026-10-01 10:00:00',
    status: 'todo',
    segs: 2,
    named: 1,
    pages: 10,
    mats: 1,
    types: ['pdf'],
    compose: '上传',
  }
}

function makeDetail(id: number, subject: string): InboxMessageDetail {
  return {
    ...makePack(id, subject),
    body_text: '',
    body_html: '',
    attachments: [],
    draft_state: {},
  }
}

function setup() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return { queryClient, invalidateSpy, wrapper }
}

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('useMaterialPacks 查询', () => {
  it('挂载即拉列表，数据原样透传（含拆分进度字段）', async () => {
    const packs = [makePack(1, '起诉状材料'), makePack(2, '证据材料')]
    listMock.mockResolvedValue(packs)
    const { wrapper } = setup()
    const { result } = renderHook(() => useMaterialPacks(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(listMock).toHaveBeenCalledTimes(1)
    expect(result.current.data).toBe(packs)
    expect(result.current.data?.[0]).toMatchObject({ subject: '起诉状材料', segs: 2, named: 1 })
  })

  it('列表失败：error 就位、data 为 undefined（调用方渲染兜底）', async () => {
    listMock.mockRejectedValue(new Error('后端不可达'))
    const { wrapper } = setup()
    const { result } = renderHook(() => useMaterialPacks(), { wrapper })
    await waitFor(() => expect(result.current.isError).toBe(true))
    expect(result.current.data).toBeUndefined()
    expect(result.current.error).toBeInstanceOf(Error)
  })

  it('查询配置：staleTime 30s、窗口 focus 不重拉（收件箱不频繁变）', async () => {
    const packs = [makePack(1, '材料')]
    listMock.mockResolvedValue(packs)
    const { queryClient, wrapper } = setup()
    const { result } = renderHook(() => useMaterialPacks(), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const query = queryClient.getQueryCache().find({ queryKey: PACKS_KEY })
    // options 的联合类型未暴露 staleTime / refetchOnWindowFocus，按实际配置字段收窄读
    const opts = query?.options as { staleTime?: number; refetchOnWindowFocus?: boolean }
    expect(opts?.staleTime).toBe(30_000)
    expect(opts?.refetchOnWindowFocus).toBe(false)

    // 行为侧验证：聚焦事件不触发第二次请求
    act(() => {
      window.dispatchEvent(new Event('focus'))
    })
    await act(async () => {
      await Promise.resolve()
    })
    expect(listMock).toHaveBeenCalledTimes(1)
  })
})

describe('useCreatePack', () => {
  it('mutateAsync 把 File[] 下推 uploadPack，成功后失效 PACKS_KEY', async () => {
    uploadMock.mockResolvedValue(makeDetail(1, '新包'))
    const files = [new File(['a'], 'a.pdf')]
    const { invalidateSpy, wrapper } = setup()
    const { result } = renderHook(() => useCreatePack(), { wrapper })
    await result.current.mutateAsync(files)
    expect(uploadMock).toHaveBeenCalledWith(files)
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: PACKS_KEY })
  })

  it('uploadPack 失败：错误向上抛（调用方 toast），不触发失效', async () => {
    uploadMock.mockRejectedValue(new Error('上传超时'))
    const { invalidateSpy, wrapper } = setup()
    const { result } = renderHook(() => useCreatePack(), { wrapper })
    await expect(result.current.mutateAsync([new File(['a'], 'a.pdf')])).rejects.toThrow('上传超时')
    expect(invalidateSpy).not.toHaveBeenCalled()
  })
})

describe('useJudgePack', () => {
  it('打标参数下推 setPackStatusRemote（id / status / assign），成功后失效列表', async () => {
    setStatusMock.mockResolvedValue(undefined)
    const { invalidateSpy, wrapper } = setup()
    const { result } = renderHook(() => useJudgePack(), { wrapper })
    const assign = { target: 'existing' as const, caseId: 9 }
    await result.current.mutateAsync({ id: 3, status: 'done', assign })
    expect(setStatusMock).toHaveBeenCalledWith(3, 'done', assign)
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: PACKS_KEY })
  })

  it('返回值附带 invalidate 方法：可手动触发列表失效（远程成功但需强制刷新时）', async () => {
    setStatusMock.mockResolvedValue(undefined)
    const { invalidateSpy, wrapper } = setup()
    const { result } = renderHook(() => useJudgePack(), { wrapper })
    expect(typeof result.current.invalidate).toBe('function')
    act(() => {
      result.current.invalidate()
    })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: PACKS_KEY })
  })
})

describe('useDeletePack', () => {
  it('删除委托 deletePack(id)，成功后失效列表', async () => {
    deleteMock.mockResolvedValue({ ok: true, message_id: 3 })
    const { invalidateSpy, wrapper } = setup()
    const { result } = renderHook(() => useDeletePack(), { wrapper })
    await result.current.mutateAsync(3)
    expect(deleteMock).toHaveBeenCalledWith(3)
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: PACKS_KEY })
  })
})

describe('useRenamePack', () => {
  it('重命名委托 renamePack(id, subject)，成功后失效列表', async () => {
    renameMock.mockResolvedValue({ ok: true, message_id: 3, subject: '新标题' })
    const { invalidateSpy, wrapper } = setup()
    const { result } = renderHook(() => useRenamePack(), { wrapper })
    await result.current.mutateAsync({ id: 3, subject: '新标题' })
    expect(renameMock).toHaveBeenCalledWith(3, '新标题')
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: PACKS_KEY })
  })
})
