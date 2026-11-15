// @vitest-environment jsdom
/**
 * 「待认领」卡同步按钮测试（jsdom）。
 *
 * 这个按钮是空态卡片唯一的即时出口，所以三件事都要对：
 * - **按完必须轮询**：后端先同步补扫已入库邮件，再提交 IMAP 异步拉新邮件，
 *   后者要几十秒。只调一次并刷新一次，用户会看到「同步了但什么都没出现」；
 * - **三种结果文案互相区分**：「收进 N 条」/「已提交邮箱同步，稍后自动出现」/
 *   「最近 1 天没有新的」——把「等异步」报成「没有」会让用户以为确实没有；
 * - **在途时不重复提交**：多份邮件扫描串起来跑是白烧 IMAP 配额。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({ syncPendingIntakes: vi.fn() }))
/** 真实 syncPendingIntakes 走 @/lib/api 建的客户端，这里记下它发了什么 */
const calls = vi.hoisted(() => [] as unknown[][])
const clientMock = vi.hoisted(() => ({
  post: vi.fn((path: string, opts: unknown) => {
    calls.push([path, opts])
    const p = Promise.resolve({ days: 1, payment_created: 0, invoice_created: 0, sources_submitted: 0 })
    return Object.assign(p, { json: () => p })
  }),
}))
const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }))

vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api')>()),
  ...apiMock,
}))
vi.mock('@/lib/api', () => ({
  createApiClient: () => clientMock,
  getApiBaseUrl: () => '/api/v1',
}))
vi.mock('sonner', () => ({ toast: toastMock }))

import { syncPendingIntakes } from '../api/pending-sync'
import { PendingSyncButton } from './PendingSyncButton'

function wrap(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

function renderButton() {
  return render(wrap(<PendingSyncButton />))
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers({ shouldAdvanceTime: true })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('PendingSyncButton：结果文案', () => {
  it('两类都收到时按类报数（款项与发票不能混成一个数字）', async () => {
    apiMock.syncPendingIntakes.mockResolvedValue({
      days: 1,
      payment_created: 2,
      invoice_created: 3,
      sources_submitted: 0,
    })
    renderButton()
    fireEvent.click(screen.getByRole('button', { name: /同步/ }))

    await waitFor(() => expect(toastMock.success).toHaveBeenCalledWith('已收进 2 笔款项、3 张发票'))
    expect(apiMock.syncPendingIntakes).toHaveBeenCalledWith(1)
  })

  it('只收到一类时不写「0 笔款项」这种空话', async () => {
    apiMock.syncPendingIntakes.mockResolvedValue({
      days: 1,
      payment_created: 0,
      invoice_created: 4,
      sources_submitted: 0,
    })
    renderButton()
    fireEvent.click(screen.getByRole('button', { name: /同步/ }))

    await waitFor(() => expect(toastMock.success).toHaveBeenCalledWith('已收进 4 张发票'))
  })

  it('已入库没新东西但还在等邮箱拉取 → 说「稍后会自动出现」，不报成没有', async () => {
    apiMock.syncPendingIntakes.mockResolvedValue({
      days: 1,
      payment_created: 0,
      invoice_created: 0,
      sources_submitted: 2,
    })
    renderButton()
    fireEvent.click(screen.getByRole('button', { name: /同步/ }))

    await waitFor(() =>
      expect(toastMock.info).toHaveBeenCalledWith('已提交邮箱同步，稍后若收到新通知会自动出现在这里'),
    )
  })

  it('确实没有新东西时才说没有', async () => {
    apiMock.syncPendingIntakes.mockResolvedValue({
      days: 1,
      payment_created: 0,
      invoice_created: 0,
      sources_submitted: 0,
    })
    renderButton()
    fireEvent.click(screen.getByRole('button', { name: /同步/ }))

    await waitFor(() => expect(toastMock.info).toHaveBeenCalledWith('最近 1 天没有新的到账或发票'))
  })
})

describe('PendingSyncButton：失败与在途', () => {
  it('失败给可行动的错误提示，不把内部错误抛给用户', async () => {
    apiMock.syncPendingIntakes.mockRejectedValue(new Error('mailbox login failed'))
    renderButton()
    fireEvent.click(screen.getByRole('button', { name: /同步/ }))

    await waitFor(() => expect(toastMock.error).toHaveBeenCalled())
    expect(toastMock.success).not.toHaveBeenCalled()
  })

  it('在途时按钮禁用并显示「同步中」，重复点击不再打接口（IMAP 配额不是免费的）', async () => {
    let resolveSync: (v: unknown) => void = () => {}
    apiMock.syncPendingIntakes.mockImplementation(
      () => new Promise((resolve) => {
        resolveSync = resolve
      }),
    )
    renderButton()
    fireEvent.click(screen.getByRole('button', { name: /同步/ }))

    const busy = screen.getByRole('button', { name: /同步中/ }) as HTMLButtonElement
    expect(busy.disabled).toBe(true)
    fireEvent.click(busy)
    expect(apiMock.syncPendingIntakes).toHaveBeenCalledTimes(1)

    resolveSync({ days: 1, payment_created: 0, invoice_created: 0, sources_submitted: 0 })
    await waitFor(() => expect(screen.getByRole('button', { name: /^同步$/ })).toBeTruthy())
  })
})

describe('syncPendingIntakes：请求口径', () => {
  /**
   * 前缀写错会 404，而「补扫几天」是服务端编排的输入：默认 1 天是产品决定
   * （拉太多会把老邮件重新收进来）。这里锁的是请求形状本身，
   * 401/刷新那条链路由 @/lib/api 的既有测试覆盖，不在本文件重复。
   */
  it('POST sync-pending，days 以字符串放进 query（后端按 query 读）', async () => {
    const response = await syncPendingIntakes()
    const [path, opts] = (calls.at(-1) ?? []) as [string, { searchParams: Record<string, string> }]
    expect(path).toBe('sync-pending')
    expect(opts.searchParams).toEqual({ days: '1' })
    expect(response).toBeTruthy()
  })

  it('显式传天数时按传入值发（调用方要补扫更久时不必改本函数）', async () => {
    await syncPendingIntakes(7)
    const [path, opts] = (calls.at(-1) ?? []) as [string, { searchParams: Record<string, string> }]
    expect(path).toBe('sync-pending')
    expect(opts.searchParams).toEqual({ days: '7' })
  })
})
