// @vitest-environment jsdom
/**
 * PaymentInvoiceZone：记收款第③节「发票」。
 *
 * 两种真实流程在这里汇合，断言就是围绕它们的区别：
 * - **收款还没保存**（paymentId = null）→ 拖票走「先开票」：传到合同名下、不归属收款
 * - **收款已保存** → 拖票直接挂这笔收款；下方再列「合同下未关联收款的票」可一键关联
 * - 金额与收款相同的未关联票标「金额吻合」，帮律师一眼对上
 * - 重复发票号只提示不计入金额；部分失败逐张带原因
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  attachPaymentInvoice: vi.fn(),
  contractInvoiceKeys: {
    all: (id: number) => ['contract-invoices', id],
    unlinked: (id: number) => ['contract-invoices', id, 'unlinked'],
  },
  copyInvoiceToClipboard: vi.fn(),
  listContractInvoices: vi.fn(),
  listPaymentInvoices: vi.fn(),
  uploadContractInvoices: vi.fn(),
  uploadPaymentInvoices: vi.fn(),
}))

vi.mock('../../api', () => apiMock)
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))
vi.mock('@/lib/clipboard', () => ({ copyText: vi.fn(async () => true) }))

import { toast } from 'sonner'

import { PaymentInvoiceZone } from './PaymentInvoiceZone'

function invoice(over: Record<string, unknown> = {}) {
  return {
    id: 1,
    payment_id: null,
    original_filename: 'a.pdf',
    display_filename: '票1.pdf',
    file_url: '/f/1',
    invoice_code: '',
    invoice_number: '0001',
    invoice_date: null,
    amount: null,
    tax_amount: null,
    total_amount: '9000',
    seller_name: '',
    buyer_name: '',
    uploaded_at: '',
    ...over,
  }
}

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

function setup(over: Partial<Parameters<typeof PaymentInvoiceZone>[0]> = {}) {
  const props = { contractId: 7, paymentId: null, paymentAmount: null, onChanged: vi.fn(), ...over }
  const view = render(<PaymentInvoiceZone {...props} />, { wrapper: wrapper() })
  return { ...props, ...view }
}

/** 走 file input（隐藏 input 的 change 是真实用户路径） */
function pickFiles(files: File[]) {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  Object.defineProperty(input, 'files', { value: files, configurable: true })
  fireEvent.change(input)
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.listContractInvoices.mockResolvedValue([])
  apiMock.listPaymentInvoices.mockResolvedValue([])
})

describe('收款未保存（先开票后付款）', () => {
  it('文案提示「钱没到也能先传」', () => {
    setup()
    expect(screen.getByText('钱没到也能先传——票挂合同名下，保存收款后一键关联')).toBeTruthy()
  })

  it('上传走合同名下端点，提示「收款后可关联」', async () => {
    apiMock.uploadContractInvoices.mockResolvedValue({
      saved: [invoice()],
      failed: [],
      duplicated_count: 0,
    })
    setup()
    pickFiles([new File(['x'], 'a.pdf', { type: 'application/pdf' })])
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('已传 1 张发票到合同名下，收款后可关联'),
    )
    expect(apiMock.uploadContractInvoices).toHaveBeenCalledWith(7, expect.any(Array))
    expect(apiMock.uploadPaymentInvoices).not.toHaveBeenCalled()
  })

  it('收款的发票列表不请求（还没有 paymentId）', async () => {
    setup()
    await waitFor(() => expect(apiMock.listContractInvoices).toHaveBeenCalled())
    expect(apiMock.listPaymentInvoices).not.toHaveBeenCalled()
  })
})

describe('收款已保存（先付款后开票）', () => {
  it('文案改为「直接归到这笔收款」，上传走收款端点', async () => {
    apiMock.uploadPaymentInvoices.mockResolvedValue({ saved: [invoice()], failed: [], duplicated_count: 0 })
    setup({ paymentId: 55 })
    expect(screen.getByText('拖入或点击上传，直接归到这笔收款')).toBeTruthy()
    pickFiles([new File(['x'], 'a.pdf', { type: 'application/pdf' })])
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('已识别并归档 1 张发票'))
    expect(apiMock.uploadPaymentInvoices).toHaveBeenCalledWith(55, expect.any(Array))
  })

  it('列出这笔收款下已有的发票（金额或「金额未识别」）', async () => {
    apiMock.listPaymentInvoices.mockResolvedValue([
      invoice({ id: 1, display_filename: '已挂1.pdf', total_amount: '9000' }),
      invoice({ id: 2, display_filename: '已挂2.pdf', total_amount: null }),
    ])
    setup({ paymentId: 55 })
    await waitFor(() => expect(screen.getByText('这笔收款的发票')).toBeTruthy())
    expect(screen.getByText('已挂1.pdf')).toBeTruthy()
    expect(screen.getByText('¥9000')).toBeTruthy()
    expect(screen.getByText('金额未识别')).toBeTruthy()
  })

  it('合同下未关联的票标「金额吻合」并可一键关联', async () => {
    apiMock.listContractInvoices.mockResolvedValue([invoice({ id: 9, display_filename: '池票.pdf', total_amount: '9000' })])
    apiMock.attachPaymentInvoice.mockResolvedValue({})
    setup({ paymentId: 55, paymentAmount: 9000 })
    await waitFor(() => expect(screen.getByText('合同下未关联收款的发票 · 1 张')).toBeTruthy())
    expect(screen.getByText('金额吻合')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /关联/ }))
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('发票已关联到这笔收款'))
    expect(apiMock.attachPaymentInvoice).toHaveBeenCalledWith(9, 55)
  })

  it('金额不同时不标「金额吻合」', async () => {
    apiMock.listContractInvoices.mockResolvedValue([invoice({ id: 9, display_filename: '池票.pdf', total_amount: '1000' })])
    setup({ paymentId: 55, paymentAmount: 9000 })
    await waitFor(() => expect(screen.getByText('池票.pdf')).toBeTruthy())
    expect(screen.queryByText('金额吻合')).toBeNull()
  })

  it('关联失败显示原因', async () => {
    apiMock.listContractInvoices.mockResolvedValue([invoice({ id: 9, display_filename: '池票.pdf' })])
    apiMock.attachPaymentInvoice.mockRejectedValue(new Error('已归属其它收款'))
    setup({ paymentId: 55, paymentAmount: 9000 })
    await waitFor(() => expect(screen.getByText('池票.pdf')).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: /关联/ }))
    await waitFor(() => expect(screen.getByText('已归属其它收款')).toBeTruthy())
  })
})

describe('上传结果处理', () => {
  it('部分失败逐张带原因显示', async () => {
    apiMock.uploadContractInvoices.mockResolvedValue({
      saved: [],
      failed: [
        { filename: 'a.pdf', reason: '不是发票' },
        { filename: 'b.pdf', reason: '已加密' },
      ],
      duplicated_count: 0,
    })
    setup()
    pickFiles([new File(['x'], 'a.pdf'), new File(['y'], 'b.pdf')])
    await waitFor(() => expect(screen.getByText('a.pdf：不是发票；b.pdf：已加密')).toBeTruthy())
    // 一张都没成 → 不刷成功提示
    expect(toast.success).not.toHaveBeenCalled()
  })

  it('重复发票号只提示、不重复计入', async () => {
    apiMock.uploadContractInvoices.mockResolvedValue({ saved: [], failed: [], duplicated_count: 2 })
    setup()
    pickFiles([new File(['x'], 'a.pdf')])
    await waitFor(() =>
      expect(toast.warning).toHaveBeenCalledWith('2 张发票号已存在，未重复计入开票金额'),
    )
  })

  it('上传抛错时降级提示', async () => {
    apiMock.uploadContractInvoices.mockRejectedValue(new Error('413'))
    setup()
    pickFiles([new File(['x'], 'a.pdf')])
    await waitFor(() => expect(screen.getByText('413')).toBeTruthy())
  })

  it('没有选中文件时不发请求', () => {
    setup()
    pickFiles([])
    expect(apiMock.uploadContractInvoices).not.toHaveBeenCalled()
  })
})
