// @vitest-environment jsdom
/**
 * useRevisions 单测（jsdom）。
 *
 * 覆盖复审台的核心交互契约：
 * - 加载清单；
 * - 决策走「乐观更新」——律师点采纳必须立刻生效（逐条过合同不能等网络）；
 * - 失败必须回滚（否则定稿会漏改）；
 * - 同一时刻只允许一条在提交（防连点导致状态错乱）；
 * - pendingCount 随决策实时变化。
 *
 * 状态由 react-query 承载（query 缓存 + mutation），测试必须包一层
 * QueryClientProvider；retry 关掉，否则失败用例要等默认 3 次退避。
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({
  listRevisions: vi.fn(),
  resolveRevision: vi.fn(),
  getTaskStatus: vi.fn(),
  uploadContract: vi.fn(),
  confirmParty: vi.fn(),
}))

import { listRevisions, resolveRevision } from '../api'
import type { ReviewRevision } from '../types'
import { useRevisions } from './use-revisions'

const listMock = vi.mocked(listRevisions)
const resolveMock = vi.mocked(resolveRevision)

function rev(over: Partial<ReviewRevision> = {}): ReviewRevision {
  return {
    id: 'r1',
    ordinal: 0,
    kind: 'risk',
    severity: 'high',
    title: '付款节点',
    original: '原文',
    suggested: '改法',
    reason: '依据',
    paragraph_index: 1,
    status: 'pending',
    reject_reason: '',
    ...over,
  }
}

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

beforeEach(() => {
  listMock.mockReset()
  resolveMock.mockReset()
})

describe('useRevisions', () => {
  it('加载清单并计算 pendingCount', async () => {
    listMock.mockResolvedValue({
      task_id: 't1',
      total: 2,
      pending: 2,
      accepted: 0,
      rejected: 0,
      items: [rev({ id: 'a' }), rev({ id: 'b', ordinal: 1, status: 'accepted' })],
    })

    const { result } = renderHook(() => useRevisions('t1'), { wrapper: createWrapper() })

    await waitFor(() => expect(result.current.items).toHaveLength(2))
    expect(result.current.pendingCount).toBe(1)
    expect(result.current.isLoading).toBe(false)
  })

  it('采纳：先本地生效（乐观），再提交服务端', async () => {
    listMock.mockResolvedValue({
      task_id: 't1',
      total: 1,
      pending: 1,
      accepted: 0,
      rejected: 0,
      items: [rev()],
    })
    // 让请求挂起，观察乐观更新是否先发生
    let release: (v: unknown) => void = () => {}
    resolveMock.mockReturnValue(
      new Promise((res) => {
        release = res as (v: unknown) => void
      }) as never,
    )

    const { result } = renderHook(() => useRevisions('t1'), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.items).toHaveLength(1))

    const first = result.current.items[0]
    expect(first).toBeDefined()
    act(() => {
      result.current.decide(first!, 'accept')
    })

    // 网络还没回，UI 已经是已采纳（onMutate 先把乐观态写进 query 缓存）
    await waitFor(() => expect(result.current.items[0]?.status).toBe('accepted'))
    expect(result.current.pendingCount).toBe(0)
    expect(result.current.busyId).toBe('r1')

    act(() => release({ id: 'r1', status: 'accepted', pending: 0 }))
    await waitFor(() => expect(result.current.busyId).toBeNull())
  })

  it('提交失败要回滚——律师看到的状态必须与服务端一致', async () => {
    listMock.mockResolvedValue({
      task_id: 't1',
      total: 1,
      pending: 1,
      accepted: 0,
      rejected: 0,
      items: [rev()],
    })
    resolveMock.mockRejectedValue(new Error('网络错误'))

    const { result } = renderHook(() => useRevisions('t1'), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.items).toHaveLength(1))

    const first = result.current.items[0]
    expect(first).toBeDefined()
    act(() => {
      result.current.decide(first!, 'accept')
    })

    await waitFor(() => expect(result.current.error).toBe('网络错误'))
    expect(result.current.items[0]?.status).toBe('pending')
    expect(result.current.pendingCount).toBe(1)
  })

  it('驳回带理由：理由写回本地', async () => {
    listMock.mockResolvedValue({
      task_id: 't1',
      total: 1,
      pending: 1,
      accepted: 0,
      rejected: 0,
      items: [rev()],
    })
    // 请求挂住：能观察到「理由已本地写回」这一帧
    let release: (v: unknown) => void = () => {}
    resolveMock.mockReturnValue(
      new Promise((res) => {
        release = res as (v: unknown) => void
      }) as never,
    )

    const { result } = renderHook(() => useRevisions('t1'), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.items).toHaveLength(1))

    const first = result.current.items[0]
    expect(first).toBeDefined()
    act(() => {
      result.current.decide(first!, 'reject', '客户坚持')
    })

    // 理由先本地写回（乐观），再随 resolve 请求落库
    await waitFor(() => expect(result.current.items[0]?.reject_reason).toBe('客户坚持'))
    // 服务端口径（onSettled 后会重拉）：该条已驳回
    listMock.mockResolvedValue({
      task_id: 't1',
      total: 1,
      pending: 0,
      accepted: 0,
      rejected: 1,
      items: [rev({ status: 'rejected', reject_reason: '客户坚持' })],
    })
    act(() => release({ revision_id: 'r1', status: 'rejected', pending: 0 }))
    // onSettled 会把清单重新拉一次（拿到服务端口径），在飞期间 mutation 仍 pending
    await waitFor(() => expect(listMock).toHaveBeenCalledTimes(2))
    await waitFor(() => expect(result.current.busyId).toBeNull())
    expect(resolveMock).toHaveBeenCalledWith('t1', 'r1', 'reject', '客户坚持')
  })

  it('撤销回到待决策', async () => {
    listMock.mockResolvedValue({
      task_id: 't1',
      total: 1,
      pending: 0,
      accepted: 0,
      rejected: 0,
      items: [rev({ status: 'accepted' })],
    })
    // 请求挂住：冷静态（撤销回待决策）必须在网络回包前就生效
    let release: (v: unknown) => void = () => {}
    resolveMock.mockReturnValue(
      new Promise((res) => {
        release = res as (v: unknown) => void
      }) as never,
    )

    const { result } = renderHook(() => useRevisions('t1'), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.items).toHaveLength(1))

    const first = result.current.items[0]
    expect(first).toBeDefined()
    act(() => {
      result.current.decide(first!, 'reset')
    })

    await waitFor(() => expect(result.current.items[0]?.status).toBe('pending'))
    act(() => release({ revision_id: 'r1', status: 'pending', pending: 1 }))
    await waitFor(() => expect(result.current.busyId).toBeNull())
  })

  it('提交中拒绝第二条（防连点导致状态错乱）', async () => {
    listMock.mockResolvedValue({
      task_id: 't1',
      total: 2,
      pending: 2,
      accepted: 0,
      rejected: 0,
      items: [rev({ id: 'a' }), rev({ id: 'b', ordinal: 1 })],
    })
    let release: (v: unknown) => void = () => {}
    resolveMock.mockReturnValue(
      new Promise((res) => {
        release = res as (v: unknown) => void
      }) as never,
    )

    const { result } = renderHook(() => useRevisions('t1'), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.items).toHaveLength(2))

    const first = result.current.items[0]
    expect(first).toBeDefined()
    act(() => {
      result.current.decide(first!, 'accept')
    })
    await waitFor(() => expect(result.current.busyId).toBe('a'))
    act(() => {
      // 第二条：mutation 在飞，应被忽略
      result.current.decide(result.current.items[1]!, 'accept')
    })

    expect(resolveMock).toHaveBeenCalledTimes(1)
    expect(result.current.items[1]?.status).toBe('pending')

    act(() => release({ id: 'a', status: 'accepted', pending: 1 }))
    await waitFor(() => expect(result.current.busyId).toBeNull())
  })

  it('加载失败给出可读错误', async () => {
    listMock.mockRejectedValue(new Error('服务器忙'))
    const { result } = renderHook(() => useRevisions('t1'), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.error).toBe('服务器忙'))
    expect(result.current.items).toEqual([])
  })

  it('taskId 为空时不发请求', async () => {
    const { result } = renderHook(() => useRevisions(null), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(listMock).not.toHaveBeenCalled()
  })
})
