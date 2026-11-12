// @vitest-environment jsdom
/**
 * PaymentDialog：记收款弹窗（粘凭据 → 核对 → 保存 → 发票关联）。
 *
 * 两个子区（PaymentPasteZone / PaymentInvoiceZone）用桩替掉：它们各自的文件有自己
 * 的用例，这里测的是**弹窗的编排**，尤其是几条实测踩过的坑：
 * - 「没认出字」与「链路失败」分开：后者 toast（调不通），前者是表单提示（图糊了），
 *   混在一起会让律师误以为服务没通、反复重拍
 * - 大小写金额冲突**不拦保存**，但必须醒目（否则成静默错账）
 * - 只有一笔收款时自动把池里待归属的票挂给它；多笔交还给人判断
 * - 任何发票关联失败都不能影响「收款已记录」这个既成事实
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  attachPaymentInvoice: vi.fn(),
  contractInvoiceKeys: { all: (id: number) => ['contract-invoices', id] },
  listContractInvoices: vi.fn(),
  listContractPayments: vi.fn(),
  parsePaymentImage: vi.fn(),
  parsePaymentText: vi.fn(),
}))
const savePaymentMock = vi.hoisted(() => vi.fn())

vi.mock('../../api', () => apiMock)
vi.mock('./payment-save', () => ({ savePayment: savePaymentMock }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))

/**
 * 子区桩：把回调摊成按钮，让用例能直接触发而不依赖子区内部实现。
 */
vi.mock('./PaymentPasteZone', () => ({
  PaymentPasteZone: (p: {
    raw: string
    imageName: string | null
    disabled: boolean
    hints: string[]
    onRawChange: (v: string) => void
    onParseText: () => void
    onPickImage: (f: File) => void
    onClearImage: () => void
  }) => (
    <div data-testid="paste-zone" data-disabled={String(p.disabled)}>
      <span data-testid="paste-image">{p.imageName ?? ''}</span>
      <span data-testid="paste-hints">{p.hints.join('|')}</span>
      <span data-testid="paste-raw">{p.raw}</span>
      <button type="button" onClick={() => p.onRawChange('到账 9,000 元')}>
        填文字
      </button>
      <button type="button" onClick={p.onParseText}>
        识别文字
      </button>
      <button type="button" onClick={() => p.onPickImage(new File(['x'], '回单.png', { type: 'image/png' }))}>
        选图片
      </button>
      <button type="button" onClick={p.onClearImage}>
        清图片
      </button>
    </div>
  ),
}))
vi.mock('./PaymentInvoiceZone', () => ({
  PaymentInvoiceZone: (p: { contractId: number; paymentId: number | null; paymentAmount: number | null }) => (
    <div data-testid="invoice-zone" data-payment-id={String(p.paymentId)} data-amount={String(p.paymentAmount)} />
  ),
}))

import { toast } from 'sonner'

import { PaymentDialog } from './PaymentDialog'

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

function setup(over: Partial<Parameters<typeof PaymentDialog>[0]> = {}) {
  const props = { open: true, contractId: 7, fixedAmount: 100000, receivedAmount: 20000, onClose: vi.fn(), onSaved: vi.fn(), ...over }
  const view = render(<PaymentDialog {...props} />, { wrapper: wrapper() })
  return { ...props, ...view }
}

/** 填好金额与日期（保存前置条件） */
function fillForm(amount = '9000') {
  fireEvent.change(screen.getByPlaceholderText('9000'), { target: { value: amount } })
  const date = document.querySelector('input[type="date"]') as HTMLInputElement
  fireEvent.change(date, { target: { value: '2026-10-20' } })
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.listContractInvoices.mockResolvedValue([])
  apiMock.listContractPayments.mockResolvedValue([])
})

describe('基本布局', () => {
  it('标题与三个必填/可选字段、剩余可收提示', () => {
    setup()
    expect(screen.getByText('记收款')).toBeTruthy()
    expect(screen.getByText('收款金额 *')).toBeTruthy()
    expect(screen.getByText('收款日期 *')).toBeTruthy()
    expect(screen.getByText('开票金额')).toBeTruthy()
    expect(screen.getByText(/合同剩余可收/)).toBeTruthy()
    expect(screen.getByText('80,000')).toBeTruthy()
  })

  it('fixedAmount 为 null 时不显示剩余可收', () => {
    setup({ fixedAmount: null })
    expect(screen.queryByText(/合同剩余可收/)).toBeNull()
  })

  it('发票区在保存前挂合同（paymentId 为 null）', () => {
    setup()
    expect(screen.getByTestId('invoice-zone').getAttribute('data-payment-id')).toBe('null')
  })
})

describe('文字识别', () => {
  it('识别成功后回填表单与提示', async () => {
    apiMock.parsePaymentText.mockResolvedValue({
      amount: '9000',
      received_at: '2026-10-20',
      payer: '某某银行',
      note: '首付款',
      hints: ['金额已核对'],
    })
    setup()
    fireEvent.click(screen.getByRole('button', { name: '填文字' }))
    fireEvent.click(screen.getByRole('button', { name: '识别文字' }))
    await waitFor(() => expect((screen.getByPlaceholderText('9000') as HTMLInputElement).value).toBe('9000'))
    expect(screen.getByTestId('paste-hints').textContent).toBe('金额已核对')
    expect((document.querySelector('input[type="date"]') as HTMLInputElement).value).toBe('2026-10-20')
  })

  it('没认出金额时提示手填（不是 toast）', async () => {
    apiMock.parsePaymentText.mockResolvedValue({ amount: null, received_at: null, payer: '', note: '', hints: [] })
    setup()
    fireEvent.click(screen.getByRole('button', { name: '填文字' }))
    fireEvent.click(screen.getByRole('button', { name: '识别文字' }))
    await waitFor(() => expect(screen.getByText('没认出金额，请手动填写')).toBeTruthy())
  })

  it('识别接口失败时给降级文案', async () => {
    apiMock.parsePaymentText.mockRejectedValue(new Error('429'))
    setup()
    fireEvent.click(screen.getByRole('button', { name: '填文字' }))
    fireEvent.click(screen.getByRole('button', { name: '识别文字' }))
    await waitFor(() => expect(screen.getByText('429')).toBeTruthy())
  })

  it('空文字不发请求', async () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: '识别文字' }))
    expect(apiMock.parsePaymentText).not.toHaveBeenCalled()
  })
})

describe('图片识别', () => {
  it('成功时回填表单、把原文贴回输入框、记住图名', async () => {
    apiMock.parsePaymentImage.mockResolvedValue({
      amount: '9000',
      received_at: '2026-10-20',
      payer: '某某银行',
      payee: '某律所',
      note: '律师费',
      hints: [],
      amount_mismatch: false,
      is_receipt: true,
      extraction_method: 'vlm',
      text: '回单原文……',
    })
    setup()
    fireEvent.click(screen.getByRole('button', { name: '选图片' }))
    await waitFor(() => expect((screen.getByPlaceholderText('9000') as HTMLInputElement).value).toBe('9000'))
    expect(screen.getByTestId('paste-image').textContent).toBe('回单.png')
    expect(screen.getByTestId('paste-raw').textContent).toBe('回单原文……')
  })

  it('大小写金额冲突：不拦保存，但弹 warning 并在表单上留醒目提示', async () => {
    apiMock.parsePaymentImage.mockResolvedValue({
      amount: '9000',
      received_at: '2026-10-20',
      payer: '',
      payee: '',
      note: '',
      hints: [],
      amount_mismatch: true,
      is_receipt: true,
      extraction_method: 'vlm',
      text: 'x',
    })
    setup()
    fireEvent.click(screen.getByRole('button', { name: '选图片' }))
    await waitFor(() => expect(toast.warning).toHaveBeenCalledWith('回单上的大写与小写金额不一致，请核对原件'))
    expect(screen.getByText('回单上的大写与小写金额不一致，请对照原件确认金额后再保存。')).toBeTruthy()
    // 保存按钮仍在
    expect(screen.getByRole('button', { name: /保存收款/ })).toBeTruthy()
  })

  it('没读出文字 → 表单提示重拍或手填（与「调不通」区分开）', async () => {
    apiMock.parsePaymentImage.mockResolvedValue({
      amount: null,
      received_at: null,
      payer: '',
      payee: '',
      note: '',
      hints: [],
      amount_mismatch: false,
      is_receipt: false,
      extraction_method: 'empty',
      text: '',
    })
    setup()
    fireEvent.click(screen.getByRole('button', { name: '选图片' }))
    await waitFor(() => expect(screen.getByText('这张图没读出文字，请重拍或手动填写')).toBeTruthy())
    expect(toast.error).not.toHaveBeenCalled()
  })

  it('有文字但没认出金额 → 另一条提示', async () => {
    apiMock.parsePaymentImage.mockResolvedValue({
      amount: null,
      received_at: null,
      payer: '',
      payee: '',
      note: '',
      hints: [],
      amount_mismatch: false,
      is_receipt: true,
      extraction_method: 'vlm',
      text: '读到一些字',
    })
    setup()
    fireEvent.click(screen.getByRole('button', { name: '选图片' }))
    await waitFor(() => expect(screen.getByText('没认出金额，请手动填写')).toBeTruthy())
  })

  it('链路失败 → toast.error 并清掉图名（别让人以为这张图已识别）', async () => {
    apiMock.parsePaymentImage.mockRejectedValue(new Error('服务未启动'))
    setup()
    fireEvent.click(screen.getByRole('button', { name: '选图片' }))
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('服务未启动'))
    expect(screen.getByTestId('paste-image').textContent).toBe('')
  })

  it('「清图片」清掉图名与冲突提示', async () => {
    apiMock.parsePaymentImage.mockResolvedValue({
      amount: '9000',
      received_at: '',
      payer: '',
      payee: '',
      note: '',
      hints: ['h'],
      amount_mismatch: true,
      is_receipt: true,
      extraction_method: 'vlm',
      text: 'x',
    })
    setup()
    fireEvent.click(screen.getByRole('button', { name: '选图片' }))
    await waitFor(() => expect(screen.getByText(/大写与小写金额不一致，请对照原件确认/)).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '清图片' }))
    expect(screen.getByTestId('paste-image').textContent).toBe('')
    expect(screen.queryByText(/大写与小写金额不一致，请对照原件确认/)).toBeNull()
  })
})

describe('保存', () => {
  it('校验不过时只提示、不落库', async () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /保存收款/ }))
    await waitFor(() => expect(screen.getByText('请填写收款金额')).toBeTruthy())
    expect(savePaymentMock).not.toHaveBeenCalled()
  })

  it('保存成功：立刻 onSaved、提示已记录、发票区切到该收款', async () => {
    savePaymentMock.mockResolvedValue({ id: 55, invoices: [] })
    setup()
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: /保存收款/ }))
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('收款已记录'))
    expect(savePaymentMock).toHaveBeenCalledWith(7, expect.objectContaining({ amount: '9000' }))
    expect(screen.getByTestId('invoice-zone').getAttribute('data-payment-id')).toBe('55')
    // 保存后按钮变「完成」且不再显示「保存收款」
    expect(screen.getByRole('button', { name: '完成' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /保存收款/ })).toBeNull()
  })

  it('保存失败时留在弹窗并显示错误', async () => {
    savePaymentMock.mockRejectedValue(new Error('余额校验失败'))
    setup()
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: /保存收款/ }))
    await waitFor(() => expect(screen.getByText('余额校验失败')).toBeTruthy())
    expect(screen.getByRole('button', { name: /保存收款/ })).toBeTruthy()
  })

  it('保存后表单字段锁定（金额/日期/备注 disabled）', async () => {
    savePaymentMock.mockResolvedValue({ id: 55, invoices: [] })
    setup()
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: /保存收款/ }))
    await waitFor(() => expect(screen.getByTestId('paste-zone').getAttribute('data-disabled')).toBe('true'))
    expect((screen.getByPlaceholderText('9000') as HTMLInputElement).disabled).toBe(true)
  })
})

describe('只有一笔收款时自动关联待归属发票', () => {
  // 池里的金额字段是 total_amount（splitByAmountMatch 的口径）
  const pool = [
    { id: 1, payment_id: null, display_filename: '票1.pdf', total_amount: '9000' },
    { id: 2, payment_id: null, display_filename: '票2.pdf', total_amount: '1000' },
  ]

  it('唯一收款 == 新收款时逐张挂上去，提示已自动关联', async () => {
    savePaymentMock.mockResolvedValue({ id: 55, invoices: [] })
    // 两张票金额与收款都对得上（9000 = 4000 + 5000 是业务口径，这里只要求逐张相等）
    apiMock.listContractInvoices.mockResolvedValue([
      { id: 1, payment_id: null, display_filename: '票1.pdf', total_amount: '9000' },
      { id: 2, payment_id: null, display_filename: '票2.pdf', total_amount: '9000' },
    ])
    apiMock.listContractPayments.mockResolvedValue([{ id: 55, amount: '9000' }])
    apiMock.attachPaymentInvoice.mockResolvedValue({})

    setup()
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: /保存收款/ }))
    await waitFor(() => expect(apiMock.attachPaymentInvoice).toHaveBeenCalledTimes(2))
    expect(apiMock.attachPaymentInvoice).toHaveBeenCalledWith(1, 55)
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('已自动关联 2 张发票（开票金额已对上）'))
  })

  it('部分发票金额与收款不同 → 提示可核对（不是纯成功）', async () => {
    savePaymentMock.mockResolvedValue({ id: 55, invoices: [] })
    apiMock.listContractInvoices.mockResolvedValue(pool)
    apiMock.listContractPayments.mockResolvedValue([{ id: 55, amount: '9000' }])
    apiMock.attachPaymentInvoice.mockResolvedValue({})

    setup()
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: /保存收款/ }))
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith(expect.stringContaining('其中 1 张金额与收款不同')))
  })

  it('多笔收款时不自动挂（交还给人判断）', async () => {
    savePaymentMock.mockResolvedValue({ id: 55, invoices: [] })
    apiMock.listContractInvoices.mockResolvedValue(pool)
    apiMock.listContractPayments.mockResolvedValue([
      { id: 55, amount: '9000' },
      { id: 56, amount: '1000' },
    ])

    setup()
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: /保存收款/ }))
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('收款已记录'))
    expect(apiMock.attachPaymentInvoice).not.toHaveBeenCalled()
  })

  it('自动关联失败只提示、不影响「收款已记录」', async () => {
    savePaymentMock.mockResolvedValue({ id: 55, invoices: [] })
    apiMock.listContractInvoices.mockRejectedValue(new Error('池查询失败'))

    setup()
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: /保存收款/ }))
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('收款已记录'))
    await waitFor(() => expect(screen.getByText('池查询失败')).toBeTruthy())
  })

  it('单张关联失败时列出未成功的发票名与原因', async () => {
    savePaymentMock.mockResolvedValue({ id: 55, invoices: [] })
    apiMock.listContractInvoices.mockResolvedValue(pool)
    apiMock.listContractPayments.mockResolvedValue([{ id: 55, amount: '9000' }])
    apiMock.attachPaymentInvoice.mockRejectedValueOnce(new Error('已归属')).mockResolvedValue({})

    setup()
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: /保存收款/ }))
    await waitFor(() => expect(screen.getByText(/有 1 张发票未能自动关联：票1\.pdf：已归属/)).toBeTruthy())
  })

  it('池里没有待归属发票时不提示（不刷无意义的成功）', async () => {
    savePaymentMock.mockResolvedValue({ id: 55, invoices: [] })
    apiMock.listContractInvoices.mockResolvedValue([])
    apiMock.listContractPayments.mockResolvedValue([{ id: 55, amount: '9000' }])

    setup()
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: /保存收款/ }))
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('收款已记录'))
    expect(toast.success).toHaveBeenCalledTimes(1)
  })
})

describe('关闭', () => {
  it('保存前「取消」直接关', () => {
    const { onClose } = setup()
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('open=false 时不渲染内容', () => {
    setup({ open: false })
    expect(screen.queryByText('记收款')).toBeNull()
  })
})
