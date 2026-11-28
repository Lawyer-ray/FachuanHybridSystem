// @vitest-environment jsdom
/**
 * InvoicePoolDialog：先开票后付款里「票挂在合同名下」的那个列表。
 *
 * 两件事是本文件存在的理由（都是用户踩出来的）：
 * 1. **删除不可一键生效**：后端连磁盘文件一起删、没有撤销；同一页的文件夹删除
 *    却是「行内确认 + 移入 _已删除可找回」。同一个「删除」不能两套口径。
 * 2. **读取失败不是「没有发票」**：以前 `pool = data ?? []` 把错误吞成空列表，
 *    律师会以为票丢了，再传一遍。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  listContractInvoices: vi.fn(),
  deletePaymentInvoice: vi.fn(),
  uploadContractInvoices: vi.fn(),
}))
vi.mock('../../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api')>()),
  ...api,
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } }))

import { InvoicePoolDialog } from './InvoicePoolDialog'

const INVOICE = {
  id: 11,
  display_filename: '咨询费发票.pdf',
  total_amount: '1000.00',
  payment_id: null,
  invoice_no: '123',
  issued_at: '2026-01-01',
} as never

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <InvoicePoolDialog open contractId={7} onClose={vi.fn()} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  api.deletePaymentInvoice.mockResolvedValue({})
})

describe('InvoicePoolDialog · 删除要确认', () => {
  it('点垃圾桶只是进入确认态，真删要再点一次', async () => {
    api.listContractInvoices.mockResolvedValue([INVOICE])
    renderDialog()

    const trash = await screen.findByRole('button', { name: '删除这张发票' })
    fireEvent.click(trash)

    expect(api.deletePaymentInvoice).not.toHaveBeenCalled()
    expect(screen.getByText('删除？')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '删除' }))
    await waitFor(() => expect(api.deletePaymentInvoice).toHaveBeenCalledWith(11))
  })

  it('确认态可以取消，什么都不删', async () => {
    api.listContractInvoices.mockResolvedValue([INVOICE])
    renderDialog()

    fireEvent.click(await screen.findByRole('button', { name: '删除这张发票' }))
    fireEvent.click(screen.getByRole('button', { name: '取消' }))

    expect(api.deletePaymentInvoice).not.toHaveBeenCalled()
    expect(screen.queryByText('删除？')).toBeNull()
  })
})

describe('InvoicePoolDialog · 读取状态', () => {
  it('读取失败给错误 + 重试，不冒充「没有发票」', async () => {
    api.listContractInvoices.mockRejectedValueOnce(new Error('boom'))
    renderDialog()

    expect(await screen.findByText('发票列表读取失败')).toBeTruthy()
    const before = api.listContractInvoices.mock.calls.length
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    await waitFor(() => expect(api.listContractInvoices.mock.calls.length).toBeGreaterThan(before))
  })

  it('在途时显示读取中，而不是空白列表', async () => {
    api.listContractInvoices.mockReturnValue(new Promise(() => {}))
    renderDialog()
    expect(await screen.findByText('正在读取发票…')).toBeTruthy()
  })
})
