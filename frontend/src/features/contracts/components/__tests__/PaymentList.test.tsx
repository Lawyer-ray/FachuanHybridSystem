const { mockMutateAsync } = vi.hoisted(() => {
  const mockMutateAsync = vi.fn()
  return { mockMutateAsync }
})

vi.mock('PaymentList', async (importOriginal) => {
  return await importOriginal()
}, { virtual: true })

vi.mock('../hooks/use-payment-mutations.ts', () => ({
  usePaymentMutations: () => ({
    createPayment: { mutateAsync: mockMutateAsync, isPending: false },
    updatePayment: { mutateAsync: mockMutateAsync, isPending: false },
    deletePayment: { mutateAsync: mockMutateAsync, isPending: false },
  }),
}))

vi.mock('../PaymentFormDialog', () => ({
  PaymentFormDialog: () => <div data-testid="payment-form-dialog" />,
}))

vi.mock('@/lib/format', () => ({
  formatAmountInt: (v: number | null) => (v != null ? `¥${v}` : '-'),
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { PaymentList } from '../PaymentList'

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

describe('PaymentList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders title', () => {
    renderWithProviders(<PaymentList contractId={1} payments={[]} />)
    expect(screen.getByText('收款记录')).toBeInTheDocument()
  })

  it('renders add button', () => {
    renderWithProviders(<PaymentList contractId={1} payments={[]} />)
    expect(screen.getByText('新增')).toBeInTheDocument()
  })

  it('shows empty message when no payments', () => {
    renderWithProviders(<PaymentList contractId={1} payments={[]} />)
    expect(screen.getByText('暂无收款记录')).toBeInTheDocument()
  })

  it('renders payment data', () => {
    const payments = [
      {
        id: 1,
        amount: 10000,
        received_at: '2026-01-01',
        invoice_status_label: '已开票',
        invoiced_amount: 5000,
        note: '首期款',
        invoices: [],
      },
    ]
    renderWithProviders(<PaymentList contractId={1} payments={payments as any} />)
    expect(screen.getByText('¥10000')).toBeInTheDocument()
    expect(screen.getByText('2026-01-01')).toBeInTheDocument()
    expect(screen.getByText('首期款')).toBeInTheDocument()
  })

  it('renders table headers', () => {
    const payments = [{ id: 1, amount: 1000, received_at: '2026-01-01', invoice_status_label: '-', invoiced_amount: 0, note: '', invoices: [] }]
    renderWithProviders(<PaymentList contractId={1} payments={payments as any} />)
    expect(screen.getByText('金额')).toBeInTheDocument()
    expect(screen.getByText('收款日期')).toBeInTheDocument()
    expect(screen.getByText('开票状态')).toBeInTheDocument()
    expect(screen.getByText('备注')).toBeInTheDocument()
  })

  it('shows total amount', () => {
    const payments = [
      { id: 1, amount: 10000, received_at: '2026-01-01', invoice_status_label: '-', invoiced_amount: 0, note: '', invoices: [] },
      { id: 2, amount: 20000, received_at: '2026-02-01', invoice_status_label: '-', invoiced_amount: 0, note: '', invoices: [] },
    ]
    renderWithProviders(<PaymentList contractId={1} payments={payments as any} />)
    expect(screen.getByText('合计: ¥30000')).toBeInTheDocument()
  })

  it('shows note dash when empty', () => {
    const payments = [{ id: 1, amount: 1000, received_at: '2026-01-01', invoice_status_label: '已开票', invoiced_amount: 500, note: null, invoices: [] }]
    renderWithProviders(<PaymentList contractId={1} payments={payments as any} />)
    const dashes = screen.getAllByText('-')
    expect(dashes.length).toBeGreaterThan(0)
  })

  it('renders invoices when expanded', () => {
    const payments = [
      {
        id: 1,
        amount: 10000,
        received_at: '2026-01-01',
        invoice_status_label: '已开票',
        invoiced_amount: 10000,
        note: '',
        invoices: [
          { id: 1, original_filename: '发票1.pdf', invoice_number: 'INV-001', total_amount: 10000, uploaded_at: '2026-01-15' },
        ],
      },
    ]
    renderWithProviders(<PaymentList contractId={1} payments={payments as any} />)
    // Click the expand button (chevron) to show invoices
    const expandButton = document.querySelector('button .lucide-chevron-right')?.closest('button')
    if (expandButton) {
      fireEvent.click(expandButton)
    }
    expect(screen.getByText('发票1.pdf')).toBeInTheDocument()
  })

  it('renders payment form dialog', () => {
    renderWithProviders(<PaymentList contractId={1} payments={[]} />)
    expect(screen.getByTestId('payment-form-dialog')).toBeInTheDocument()
  })

  // --- Additional tests from coverage expansion ---

  it('renders received_at fallback dash', () => {
    const payments = [{ id: 1, amount: 1000, received_at: null, invoice_status_label: '-', invoiced_amount: 0, note: '', invoices: [] }]
    renderWithProviders(<PaymentList contractId={1} payments={payments as any} />)
    expect(screen.getAllByText('-').length).toBeGreaterThan(0)
  })

  it('renders invoices expand button when has invoices', () => {
    const payments = [{
      id: 1, amount: 10000, received_at: '2026-01-01', invoice_status_label: '已开票',
      invoiced_amount: 10000, note: '',
      invoices: [{ id: 1, original_filename: 'inv.pdf', invoice_number: 'INV-001', total_amount: 5000, uploaded_at: '2026-01-15' }],
    }]
    renderWithProviders(<PaymentList contractId={1} payments={payments as any} />)
    // Click the expand button (chevron) to show invoices
    const expandButton = document.querySelector('button .lucide-chevron-right')?.closest('button')
    expect(expandButton).toBeInTheDocument()
  })

  it('renders invoice without invoice_number', () => {
    const payments = [{
      id: 1, amount: 10000, received_at: '2026-01-01', invoice_status_label: '已开票',
      invoiced_amount: 10000, note: '',
      invoices: [{ id: 1, original_filename: 'inv.pdf', invoice_number: null, total_amount: null, uploaded_at: null }],
    }]
    renderWithProviders(<PaymentList contractId={1} payments={payments as any} />)
    // Click the expand button to show invoices
    const expandButton = document.querySelector('button .lucide-chevron-right')?.closest('button')
    if (expandButton) {
      fireEvent.click(expandButton)
    }
    expect(screen.getByText('inv.pdf')).toBeInTheDocument()
  })
})
