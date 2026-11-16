// @vitest-environment jsdom
/**
 * 到账待认领 mutation 的行为锁定（jsdom + react-query）。
 *
 * 重点不是「调用了 api」而是**四个裁定动作彼此不能串**：confirm 会真的写一条
 * 收款记录（钱落到项目上），reject 说「这不是记账事件」，ignore 说「这笔不用
 * 记账」，三个动作在用户眼里是三句完全不同的话，在后端是三个端点。串了不会
 * 报错——`useIgnoreIntake` 误接 `rejectIntake`，请求照样 200，只是这笔往来款
 * 从此被归类成「非记账事件」，财务对账时才发现口径错了。
 *
 * 所以每个 mutation 都断言到「端点 + 默认文案 + 失败文案」三层，并用
 * `toHaveBeenCalledWith` 校验 note/reason 的透传。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('../api', () => ({
  INTAKE_PENDING_KEY: ['payment-intake-pending'],
  INTAKE_COUNT_KEY: ['payment-intake-count'],
  INTAKE_SELECTABLE_KEY: ['payment-intake-selectable'],
  listPendingIntakes: vi.fn(),
  getPendingCount: vi.fn(),
  confirmIntake: vi.fn(),
  rejectIntake: vi.fn(),
  ignoreIntake: vi.fn(),
  reopenIntake: vi.fn(),
}))

import { toast } from 'sonner'

import * as api from '../api'
import {
  useConfirmIntake,
  useIgnoreIntake,
  usePendingIntakeCount,
  usePendingIntakes,
  useRejectIntake,
  useReopenIntake,
} from './use-pending-intakes'

const mocks = {
  confirm: vi.mocked(api.confirmIntake),
  reject: vi.mocked(api.rejectIntake),
  ignore: vi.mocked(api.ignoreIntake),
  reopen: vi.mocked(api.reopenIntake),
  list: vi.mocked(api.listPendingIntakes),
  count: vi.mocked(api.getPendingCount),
}

function actionResult(over: Record<string, unknown> = {}) {
  return { success: true, intake_id: 7, message: '', ...over } as never
}

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { client, wrapper }
}

function countInvalidations(client: QueryClient, keyHead: string): number {
  return vi
    .mocked(client.invalidateQueries)
    .mock.calls.filter(([filters]) => String((filters as { queryKey?: unknown })?.queryKey) === keyHead).length
}

let client: QueryClient
let wrapper: ({ children }: { children: ReactNode }) => ReactNode

beforeEach(() => {
  vi.clearAllMocks()
  const created = createWrapper()
  client = created.client
  wrapper = created.wrapper
  vi.spyOn(client, 'invalidateQueries').mockResolvedValue()
})

describe('usePendingIntakes / usePendingIntakeCount：数据源', () => {
  it('列表按 limit 取数', async () => {
    mocks.list.mockResolvedValue([])
    const { result } = renderHook(() => usePendingIntakes(8), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(mocks.list).toHaveBeenCalledWith(8)
  })

  it('角标只打 pending/count', async () => {
    mocks.count.mockResolvedValue(2)
    const { result } = renderHook(() => usePendingIntakeCount(), { wrapper })
    await waitFor(() => expect(result.current.data).toBe(2))
    expect(mocks.list).not.toHaveBeenCalled()
  })
})

describe('useConfirmIntake', () => {
  it('透传 contractId/note 并刷新列表与角标；缺 message 时提示「已写入收款记录」', async () => {
    mocks.confirm.mockResolvedValue(actionResult({ message: '' }))
    const { result } = renderHook(() => useConfirmIntake(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ id: 7, contractId: 11, note: '按判决书归属' })
    })

    expect(mocks.confirm).toHaveBeenCalledWith(7, 11, '按判决书归属')
    // 这是财务动作：文案必须让用户明确知道「收款记录已经生成」，
    // 只写「已确认」会让人不确定钱有没有落账
    expect(toast.success).toHaveBeenCalledWith('已确认并写入收款记录')
    expect(countInvalidations(client, 'payment-intake-pending')).toBe(1)
    expect(countInvalidations(client, 'payment-intake-count')).toBe(1)
  })

  it('不传 contractId（采纳系统建议）时参数为 undefined，后端按 null 处理', async () => {
    mocks.confirm.mockResolvedValue(actionResult({ message: '已确认' }))
    const { result } = renderHook(() => useConfirmIntake(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ id: 7 })
    })

    expect(mocks.confirm).toHaveBeenCalledWith(7, undefined, undefined)
    expect(toast.success).toHaveBeenCalledWith('已确认')
  })

  it('失败时透出后端报文（候选项目已失效这类原因只有后端知道）', async () => {
    mocks.confirm.mockRejectedValue({ name: 'HTTPError', data: { message: '合同已归档' } })
    const { result } = renderHook(() => useConfirmIntake(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ id: 7 }).catch(() => {})
    })

    expect(toast.error).toHaveBeenCalledWith('合同已归档')
  })
})

describe('useRejectIntake 与 useIgnoreIntake 不得混', () => {
  it('reject 打 /reject，文案「非记账事件」', async () => {
    mocks.reject.mockResolvedValue(actionResult({ message: '' }))
    const { result } = renderHook(() => useRejectIntake(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ id: 3, reason: '不是本案款项' })
    })

    expect(mocks.reject).toHaveBeenCalledWith(3, '不是本案款项')
    expect(mocks.ignore).not.toHaveBeenCalled()
    expect(toast.success).toHaveBeenCalledWith('已标记为非记账事件')
    expect(countInvalidations(client, 'payment-intake-pending')).toBe(1)
  })

  it('ignore 打 /ignore，文案「不需记账」——与 reject 是两种口径', async () => {
    mocks.ignore.mockResolvedValue(actionResult({ message: '' }))
    const { result } = renderHook(() => useIgnoreIntake(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ id: 3, reason: '客户退款往来' })
    })

    expect(mocks.ignore).toHaveBeenCalledWith(3, '客户退款往来')
    expect(mocks.reject).not.toHaveBeenCalled()
    expect(toast.success).toHaveBeenCalledWith('已标记为不需记账')
    expect(countInvalidations(client, 'payment-intake-count')).toBe(1)
  })

  it('两者的失败文案都是通用「操作失败」（无后端报文时回 fallback）', async () => {
    mocks.reject.mockRejectedValue(new Error(''))
    mocks.ignore.mockRejectedValue(new Error(''))
    const rejectHook = renderHook(() => useRejectIntake(), { wrapper })
    const ignoreHook = renderHook(() => useIgnoreIntake(), { wrapper })

    await act(async () => {
      await rejectHook.result.current.mutateAsync({ id: 3, reason: 'x' }).catch(() => {})
      await ignoreHook.result.current.mutateAsync({ id: 3, reason: 'y' }).catch(() => {})
    })

    expect(toast.error).toHaveBeenCalledTimes(2)
    expect(vi.mocked(toast.error).mock.calls.every(([msg]) => msg === '操作失败')).toBe(true)
  })
})

describe('useReopenIntake', () => {
  it('只按 id 调端点，两把 key 都刷', async () => {
    mocks.reopen.mockResolvedValue(actionResult({ message: '已撤销' }))
    const { result } = renderHook(() => useReopenIntake(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync(3)
    })

    expect(mocks.reopen).toHaveBeenCalledWith(3)
    expect(toast.success).toHaveBeenCalledWith('已撤销')
    expect(countInvalidations(client, 'payment-intake-pending')).toBe(1)
    expect(countInvalidations(client, 'payment-intake-count')).toBe(1)
  })

  it('缺 message 时补「已撤销」；失败文案是「撤销失败」而非确认失败', async () => {
    mocks.reopen.mockResolvedValue(actionResult({ message: '' }))
    const ok = renderHook(() => useReopenIntake(), { wrapper })
    await act(async () => {
      await ok.result.current.mutateAsync(3)
    })
    expect(toast.success).toHaveBeenCalledWith('已撤销')

    mocks.reopen.mockRejectedValue({ name: 'HTTPError', data: {} })
    await act(async () => {
      await ok.result.current.mutateAsync(3).catch(() => {})
    })
    expect(toast.error).toHaveBeenCalledWith('撤销失败')
  })
})
