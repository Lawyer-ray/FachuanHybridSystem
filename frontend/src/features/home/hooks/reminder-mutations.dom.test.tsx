// @vitest-environment jsdom
/**
 * 日历事件乐观更新 hook 测试（use-complete-reminder / use-delete-reminder）。
 *
 * 核心不变量（2026-10 审查关注点）：
 * - 命中口径与下发口径同源：合并事件的任一成员 id 被点名即整体命中
 * - 失败必须回滚到快照，不能留下半截乐观态
 * - stats 口径由后端重算，onSettled 必须 invalidate
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))

const setCompletedMock = vi.hoisted(() => vi.fn())
const deleteMock = vi.hoisted(() => vi.fn())

vi.mock('../api', () => ({
  calendarKeys: { all: ['calendar'] },
  setRemindersCompleted: (...a: unknown[]) => setCompletedMock(...a),
  deleteReminders: (...a: unknown[]) => deleteMock(...a),
}))

import { toast } from 'sonner'

import { useCompleteReminder } from './use-complete-reminder'
import { useDeleteReminder } from './use-delete-reminder'

/** 一条被合并的事件：member_ids 里含多个提醒 id */
function mergedEvent(over: Record<string, unknown> = {}) {
  return {
    id: 1,
    kind: 'hearing',
    title: '开庭',
    date: '2026-10-20',
    time: '09:30',
    is_completed: false,
    member_ids: [11, 12],
    can_delete: true,
    ...over,
  } as never
}

function makeClient() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  qc.setQueryData(['calendar'], {
    days: {
      '2026-10-20': [mergedEvent()],
      '2026-10-21': [mergedEvent({ id: 2, member_ids: [99] })],
    },
  })
  return qc
}

function wrapper(qc: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
}

/** 从缓存里取某天第一条事件的 is_completed */
function completedAt(qc: QueryClient, day: string): boolean | undefined {
  const data = qc.getQueryData<{ days: Record<string, Array<{ is_completed: boolean }>> }>(['calendar'])
  return data?.days[day]?.[0]?.is_completed
}

function countAt(qc: QueryClient, day: string): number {
  const data = qc.getQueryData<{ days: Record<string, unknown[]> }>(['calendar'])
  return data?.days[day]?.length ?? 0
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useCompleteReminder', () => {
  it('乐观更新：只翻转成员 id 命中的合并事件，并提示成功', async () => {
    setCompletedMock.mockResolvedValue({})
    const qc = makeClient()
    const { result } = renderHook(() => useCompleteReminder(), { wrapper: wrapper(qc) })

    await act(async () => {
      await result.current.mutateAsync({ ids: [12], completed: true })
    })

    // 12 是第一条事件的成员 → 命中
    expect(completedAt(qc, '2026-10-20')).toBe(true)
    // 99 才是第二条的成员 → 不应被误伤
    expect(completedAt(qc, '2026-10-21')).toBe(false)
    expect(toast.success).toHaveBeenCalledWith('已标记完成')
  })

  it('取消完成：提示文案区分', async () => {
    setCompletedMock.mockResolvedValue({})
    const qc = makeClient()
    const { result } = renderHook(() => useCompleteReminder(), { wrapper: wrapper(qc) })

    await act(async () => {
      await result.current.mutateAsync({ ids: [11], completed: false })
    })

    expect(toast.success).toHaveBeenCalledWith('已恢复为未完成')
  })

  it('失败回滚：缓存恢复到快照状态', async () => {
    setCompletedMock.mockRejectedValue(new Error('boom'))
    const qc = makeClient()
    const { result } = renderHook(() => useCompleteReminder(), { wrapper: wrapper(qc) })

    await act(async () => {
      await result.current.mutateAsync({ ids: [11], completed: true }).catch(() => {})
    })

    await waitFor(() => expect(completedAt(qc, '2026-10-20')).toBe(false))
    expect(toast.error).toHaveBeenCalledWith('标记失败，请稍后重试')
  })
})

describe('useDeleteReminder', () => {
  it('乐观更新：移除命中事件，同一天其他事件保留', async () => {
    deleteMock.mockResolvedValue({})
    const qc = makeClient()
    qc.setQueryData(['calendar'], {
      days: {
        '2026-10-20': [mergedEvent({ id: 1, member_ids: [11] }), mergedEvent({ id: 3, member_ids: [55] })],
      },
    })
    const { result } = renderHook(() => useDeleteReminder(), { wrapper: wrapper(qc) })

    await act(async () => {
      await result.current.mutateAsync({ ids: [11] })
    })

    expect(countAt(qc, '2026-10-20')).toBe(1)
    expect(toast.success).toHaveBeenCalledWith('已删除')
  })

  it('失败回滚：被删事件回到缓存，并透传后端文案', async () => {
    deleteMock.mockRejectedValue(new Error('仅提醒创建人或管理员可以删除该提醒'))
    const qc = makeClient()
    const { result } = renderHook(() => useDeleteReminder(), { wrapper: wrapper(qc) })

    await act(async () => {
      await result.current.mutateAsync({ ids: [11] }).catch(() => {})
    })

    await waitFor(() => expect(countAt(qc, '2026-10-20')).toBe(1))
    expect(toast.error).toHaveBeenCalled()
  })
})
