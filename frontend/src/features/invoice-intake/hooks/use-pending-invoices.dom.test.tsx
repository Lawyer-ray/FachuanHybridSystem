// @vitest-environment jsdom
/**
 * 发票待认领 mutation 的行为锁定（jsdom + react-query）。
 *
 * 为什么逐条测这 6 个 mutation 而不是只挑一两个代表：它们的 onSuccess 骨架
 * 长得一样，**差别全在「该打哪个端点、成功后对用户说什么」**。这两件事错了
 * 都不会抛异常——`useRejectInvoiceIntake` 误接 `reopenInvoiceIntake`，tcs/lint
 * 全绿、请求也成功，只是票被撤销而不是标记无关；`useConfirmRedOnly` 接错成
 * `confirmRedReenact`，账就多收一张。所以每条都断言到端点 + 文案两层。
 *
 * 另外三条是本文件的重点：
 * - `res.message || '默认文案'`：后端**不传 message** 时前端必须自己补一句，
 *   否则用户看到的是空白 toast（后端合同里 message 是可选的）。
 * - `onConfirmed` 只在 `invoice_id` 存在时触发：确认完把「刚认领的行」留在
 *   列表里供复制，没有发票 id 时没有可复制的落点，回调就不能被调用。
 * - 每个 mutation 都要同时打 PENDING 与 COUNT 两个 key：只刷列表不刷角标，
 *   首页会显示「待认领 3」而列表已经空了。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('../api', () => ({
  INVOICE_INTAKE_PENDING_KEY: ['invoice-intake-pending'],
  INVOICE_INTAKE_COUNT_KEY: ['invoice-intake-count'],
  INVOICE_SELECTABLE_KEY: ['invoice-intake-selectable'],
  listPendingInvoices: vi.fn(),
  getPendingInvoiceCount: vi.fn(),
  confirmInvoiceIntake: vi.fn(),
  rejectInvoiceIntake: vi.fn(),
  reopenInvoiceIntake: vi.fn(),
  confirmRedReenact: vi.fn(),
  confirmRedOnly: vi.fn(),
  reparseIntake: vi.fn(),
  rescanInvoiceIntakes: vi.fn(),
}))

import { toast } from 'sonner'

import * as api from '../api'
import {
  useConfirmInvoiceIntake,
  useConfirmRedOnly,
  useConfirmRedReenact,
  usePendingInvoiceCount,
  usePendingInvoices,
  useRejectInvoiceIntake,
  useReopenInvoiceIntake,
  useReparseIntake,
} from './use-pending-invoices'

const mocks = {
  confirm: vi.mocked(api.confirmInvoiceIntake),
  reject: vi.mocked(api.rejectInvoiceIntake),
  reopen: vi.mocked(api.reopenInvoiceIntake),
  redReenact: vi.mocked(api.confirmRedReenact),
  redOnly: vi.mocked(api.confirmRedOnly),
  reparse: vi.mocked(api.reparseIntake),
  list: vi.mocked(api.listPendingInvoices),
  count: vi.mocked(api.getPendingInvoiceCount),
}

/** 后端 InvoiceActionResult 的最小形状：message 与 invoice_id 都可缺省 */
function actionResult(over: Record<string, unknown> = {}) {
  return { success: true, intake_id: 7, message: '', invoice_id: null, ...over } as never
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

/**
 * 计数某个 key 前缀被 invalidate 过几次。
 *
 * 直接看 `invalidateQueries` 的调用参数比翻缓存更准：invalidate 只标脏、
 * 有活跃观察者才重拉，光断言缓存数据会漏掉「角标没刷」这类缺陷。
 */
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

describe('usePendingInvoices / usePendingInvoiceCount：数据源', () => {
  it('列表按 limit 取数，且 query key 带 limit（换 limit 必须换缓存条目）', async () => {
    mocks.list.mockResolvedValue([])
    const { result } = renderHook(() => usePendingInvoices(5), { wrapper })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(mocks.list).toHaveBeenCalledWith(5)
  })

  it('角标只打 pending/count，不拉全量列表', async () => {
    mocks.count.mockResolvedValue(3)
    const { result } = renderHook(() => usePendingInvoiceCount(), { wrapper })
    await waitFor(() => expect(result.current.data).toBe(3))
    expect(mocks.list).not.toHaveBeenCalled()
  })
})

describe('useConfirmInvoiceIntake', () => {
  it('带 contractId/paymentId 透传给确认端点，并同时刷新列表与角标', async () => {
    mocks.confirm.mockResolvedValue(actionResult({ message: '已绑定某某公司项目' }))
    const { result } = renderHook(() => useConfirmInvoiceIntake(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ id: 7, contractId: 11, paymentId: 22 })
    })

    expect(mocks.confirm).toHaveBeenCalledWith(7, 11, 22)
    expect(toast.success).toHaveBeenCalledWith('已绑定某某公司项目')
    expect(countInvalidations(client, 'invoice-intake-pending')).toBe(1)
    expect(countInvalidations(client, 'invoice-intake-count')).toBe(1)
  })

  it('后端不传 message 时补默认文案（否则用户看到的是一片空白 toast）', async () => {
    mocks.confirm.mockResolvedValue(actionResult({ message: '' }))
    const { result } = renderHook(() => useConfirmInvoiceIntake(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ id: 7 })
    })

    expect(toast.success).toHaveBeenCalledWith('已绑定该项目')
    expect(mocks.confirm).toHaveBeenCalledWith(7, undefined, undefined)
  })

  it('有 invoice_id 才回调 onConfirmed，且 displayFilename 缺省为空串', async () => {
    mocks.confirm.mockResolvedValue(actionResult({ invoice_id: 88, message: '已绑定' }))
    const onConfirmed = vi.fn()
    const { result } = renderHook(() => useConfirmInvoiceIntake({ onConfirmed }), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ id: 7 })
    })

    // 回调参数是「刚认领那行」就地渲染成「文件名 + 复制」所需的全部信息，
    // 少一个字段调用方就得回头再查一次列表
    expect(onConfirmed).toHaveBeenCalledWith({
      intakeId: 7,
      invoiceId: 88,
      displayFilename: '',
      message: '已绑定',
    })
  })

  it('没有 invoice_id 时不回调：没有可复制的落点就不该把这行留在列表里', async () => {
    mocks.confirm.mockResolvedValue(actionResult({ invoice_id: null }))
    const onConfirmed = vi.fn()
    const { result } = renderHook(() => useConfirmInvoiceIntake({ onConfirmed }), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ id: 7 })
    })

    expect(onConfirmed).not.toHaveBeenCalled()
    expect(toast.success).toHaveBeenCalled()
  })

  it('后端报文优先透出（errMessage），失败也要 refresh？—不刷新，但文案必须是后端原话', async () => {
    mocks.confirm.mockRejectedValue({ name: 'HTTPError', data: { message: '该发票已被他人确认' } })
    const { result } = renderHook(() => useConfirmInvoiceIntake(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ id: 7 }).catch(() => {})
    })

    expect(toast.error).toHaveBeenCalledWith('该发票已被他人确认')
    expect(client.invalidateQueries).not.toHaveBeenCalled()
  })
})

describe('useRejectInvoiceIntake', () => {
  it('打 /reject 端点并透传理由；缺 message 时用「无关发票」文案', async () => {
    mocks.reject.mockResolvedValue(actionResult({ message: '' }))
    const { result } = renderHook(() => useRejectInvoiceIntake(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ id: 5, reason: '非本所项目' })
    })

    expect(mocks.reject).toHaveBeenCalledWith(5, '非本所项目')
    // 文案必须与「已撤销」区分：驳回是把票归为无关，撤销是回到待认领，
    // 两者对用户是相反的操作，用同一句话会让人以为票据回来了
    expect(toast.success).toHaveBeenCalledWith('已标记为无关发票')
    expect(countInvalidations(client, 'invoice-intake-pending')).toBe(1)
    expect(countInvalidations(client, 'invoice-intake-count')).toBe(1)
  })

  it('失败走通用「操作失败」兜底（无后端报文时 errMessage 回 fallback）', async () => {
    mocks.reject.mockRejectedValue(new Error(''))
    const { result } = renderHook(() => useRejectInvoiceIntake(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ id: 5, reason: 'x' }).catch(() => {})
    })

    expect(toast.error).toHaveBeenCalledWith('操作失败')
  })
})

describe('useConfirmRedReenact / useConfirmRedOnly', () => {
  it('冲红重开：note/amountOverride 走 hook 默认值（空串 / false）', async () => {
    mocks.redReenact.mockResolvedValue(actionResult({ message: '已冲红并重开' }))
    const { result } = renderHook(() => useConfirmRedReenact(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ id: 9, newIntakeId: 30 })
    })

    expect(mocks.redReenact).toHaveBeenCalledWith(9, 30, '', false)
    expect(toast.success).toHaveBeenCalledWith('已冲红并重开')
  })

  it('冲红重开：显式传 note 与 amountOverride 时不得被默认值盖掉', async () => {
    mocks.redReenact.mockResolvedValue(actionResult({ message: '' }))
    const { result } = renderHook(() => useConfirmRedReenact(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ id: 9, newIntakeId: null, note: '差额 200 已核', amountOverride: true })
    })

    // newIntakeId 可以是 null（组内没有蓝票可重开），此时仍走本端点
    expect(mocks.redReenact).toHaveBeenCalledWith(9, null, '差额 200 已核', true)
    expect(toast.success).toHaveBeenCalledWith('已冲红并确认重开')
  })

  it('仅冲红必须走 confirmRedOnly，不能串成 confirmRedReenact（串了账上会多收一张）', async () => {
    mocks.redOnly.mockResolvedValue(actionResult({ message: '' }))
    const { result } = renderHook(() => useConfirmRedOnly(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ id: 9 })
    })

    expect(mocks.redOnly).toHaveBeenCalledWith(9, '')
    expect(mocks.redReenact).not.toHaveBeenCalled()
    expect(toast.success).toHaveBeenCalledWith('已冲红')
  })

  it('仅冲红失败时文案是「冲红失败」而不是「冲红重开失败」', async () => {
    mocks.redOnly.mockRejectedValue({ name: 'HTTPError', data: { message: '红票金额未识别' } })
    const { result } = renderHook(() => useConfirmRedOnly(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ id: 9 }).catch(() => {})
    })

    expect(toast.error).toHaveBeenCalledWith('红票金额未识别')
  })
})

describe('useReparseIntake / useReopenInvoiceIntake', () => {
  it('重解析只按 id 调端点；缺 message 时用「已重新解析」', async () => {
    mocks.reparse.mockResolvedValue(actionResult({ message: '' }))
    const { result } = renderHook(() => useReparseIntake(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync(7)
    })

    expect(mocks.reparse).toHaveBeenCalledWith(7)
    expect(toast.success).toHaveBeenCalledWith('已重新解析')
    expect(countInvalidations(client, 'invoice-intake-pending')).toBe(1)
  })

  it('重解析失败透出后端报文（金额识别不出时后端会说明原因）', async () => {
    mocks.reparse.mockRejectedValue({ name: 'HTTPError', data: { message: 'PDF 未挂载' } })
    const { result } = renderHook(() => useReparseIntake(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync(7).catch(() => {})
    })

    expect(toast.error).toHaveBeenCalledWith('PDF 未挂载')
  })

  it('撤销：走 reopen 端点，文案「已撤销」，两个 key 都刷', async () => {
    mocks.reopen.mockResolvedValue(actionResult({ message: '' }))
    const { result } = renderHook(() => useReopenInvoiceIntake(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync(7)
    })

    expect(mocks.reopen).toHaveBeenCalledWith(7)
    expect(toast.success).toHaveBeenCalledWith('已撤销')
    expect(countInvalidations(client, 'invoice-intake-pending')).toBe(1)
    expect(countInvalidations(client, 'invoice-intake-count')).toBe(1)
  })

  it('撤销失败文案是「撤销失败」（不能与确认失败混）', async () => {
    mocks.reopen.mockRejectedValue({ name: 'HTTPError', data: {} })
    const { result } = renderHook(() => useReopenInvoiceIntake(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync(7).catch(() => {})
    })

    expect(toast.error).toHaveBeenCalledWith('撤销失败')
  })
})
