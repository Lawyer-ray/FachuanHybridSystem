import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { PaymentList } from '../components/PaymentList'
import type { ContractPayment } from '../types'

// ── Mocks ──

const mockCreatePayment = { mutateAsync: vi.fn(), isPending: false }
const mockUpdatePayment = { mutateAsync: vi.fn(), isPending: false }
const mockDeletePayment = { mutateAsync: vi.fn(), isPending: false }

vi.mock('../hooks/use-payment-mutations', () => ({
  usePaymentMutations: () => ({
    createPayment: mockCreatePayment,
    updatePayment: mockUpdatePayment,
    deletePayment: mockDeletePayment,
  }),
}))

vi.mock('../components/PaymentFormDialog', () => ({
  PaymentFormDialog: ({ open, onSubmit }: { open: boolean; onSubmit: (data: unknown) => void }) =>
    open ? <div data-testid="payment-form-dialog">Form</div> : null,
}))

vi.mock('lucide-react', () => ({
  Plus: (p: Record<string, unknown>) => <svg data-testid="plus" {...p} />,
  Edit: (p: Record<string, unknown>) => <svg data-testid="edit" {...p} />,
  Trash2: (p: Record<string, unknown>) => <svg data-testid="trash" {...p} />,
  DollarSign: (p: Record<string, unknown>) => <svg data-testid="dollar" {...p} />,
  ChevronRight: (p: Record<string, unknown>) => <svg data-testid="chevron" {...p} />,
  Receipt: (p: Record<string, unknown>) => <svg data-testid="receipt" {...p} />,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/lib/format', () => ({
  formatAmountInt: (val: number) => `¥${val.toLocaleString()}`,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardHeader: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardTitle: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
}))

vi.mock('@/components/ui/table', () => ({
  Table: ({ children }: { children: React.ReactNode }) => <table>{children}</table>,
  TableBody: ({ children }: { children: React.ReactNode }) => <tbody>{children}</tbody>,
  TableCell: ({ children, ...props }: Record<string, unknown>) => <td {...props}>{children}</td>,
  TableHead: ({ children, ...props }: Record<string, unknown>) => <th {...props}>{children}</th>,
  TableHeader: ({ children }: { children: React.ReactNode }) => <thead>{children}</thead>,
  TableRow: ({ children }: { children: React.ReactNode }) => <tr>{children}</tr>,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: Record<string, unknown>) => <span {...props}>{children}</span>,
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) =>
    open ? <div data-testid="alert-dialog">{children}</div> : null,
  AlertDialogAction: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
  AlertDialogCancel: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

// ── Helpers ──

function makePayment(overrides: Partial<ContractPayment> = {}): ContractPayment {
  return {
    id: 1,
    contract: 1,
    amount: 10000,
    received_at: '2024-01-01',
    invoice_status: 'UNINVOICED',
    invoice_status_label: '未开票',
    invoiced_amount: 0,
    note: null,
    created_at: '2024-01-01',
    updated_at: '2024-01-01',
    invoices: [],
    ...overrides,
  } as ContractPayment
}

describe('PaymentList', () => {
  beforeEach(() => {
    mockCreatePayment.mutateAsync.mockReset()
    mockUpdatePayment.mutateAsync.mockReset()
    mockDeletePayment.mutateAsync.mockReset()
  })

  it('renders empty state when no payments', () => {
    render(<PaymentList contractId={1} payments={[]} />)
    expect(screen.getByText('暂无收款记录')).toBeInTheDocument()
  })

  it('renders payment table with data', () => {
    const payments = [makePayment({ note: 'Payment 1' })]
    render(<PaymentList contractId={1} payments={payments} />)
    expect(screen.getByText('Payment 1')).toBeInTheDocument()
    expect(screen.getByText('未开票')).toBeInTheDocument()
  })

  it('renders total amount', () => {
    const payments = [
      makePayment({ id: 1, amount: 10000 }),
      makePayment({ id: 2, amount: 20000 }),
    ]
    render(<PaymentList contractId={1} payments={payments} />)
    expect(screen.getByText('合计: ¥30,000')).toBeInTheDocument()
  })

  it('renders note fallback dash', () => {
    render(<PaymentList contractId={1} payments={[makePayment({ note: null })]} />)
    expect(screen.getByText('-')).toBeInTheDocument()
  })

  it('renders received_at fallback dash', () => {
    render(<PaymentList contractId={1} payments={[makePayment({ received_at: null })]} />)
    expect(screen.getAllByText('-').length).toBeGreaterThan(0)
  })

  it('opens new payment form', () => {
    render(<PaymentList contractId={1} payments={[]} />)
    fireEvent.click(screen.getByText('新增'))
    expect(screen.getByTestId('payment-form-dialog')).toBeInTheDocument()
  })

  it('opens edit payment form', () => {
    const payments = [makePayment()]
    render(<PaymentList contractId={1} payments={payments} />)
    fireEvent.click(screen.getByTestId('edit'))
    expect(screen.getByTestId('payment-form-dialog')).toBeInTheDocument()
  })

  it('opens delete dialog', () => {
    const payments = [makePayment()]
    render(<PaymentList contractId={1} payments={payments} />)
    fireEvent.click(screen.getByTestId('trash'))
    expect(screen.getByTestId('alert-dialog')).toBeInTheDocument()
  })

  it('handles delete confirmation', async () => {
    mockDeletePayment.mutateAsync.mockResolvedValue(undefined)
    const { toast } = await import('sonner')
    const payments = [makePayment()]
    render(<PaymentList contractId={1} payments={payments} />)
    fireEvent.click(screen.getByTestId('trash'))
    const deleteBtn = screen.getByText('删除')
    fireEvent.click(deleteBtn)
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('收款已删除'))
  })

  it('handles delete error', async () => {
    mockDeletePayment.mutateAsync.mockRejectedValue(new Error('fail'))
    const { toast } = await import('sonner')
    const payments = [makePayment()]
    render(<PaymentList contractId={1} payments={payments} />)
    fireEvent.click(screen.getByTestId('trash'))
    fireEvent.click(screen.getByText('删除'))
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('删除失败'))
  })

  it('renders invoices expand button when has invoices', () => {
    const payments = [makePayment({
      invoices: [{ id: 1, original_filename: 'inv.pdf', invoice_number: 'INV-001', total_amount: 5000, uploaded_at: '2024-01-01' } as never],
    })]
    render(<PaymentList contractId={1} payments={payments} />)
    expect(screen.getByTestId('chevron')).toBeInTheDocument()
  })

  it('expands invoice rows on chevron click', () => {
    const payments = [makePayment({
      invoices: [{ id: 1, original_filename: 'inv.pdf', invoice_number: 'INV-001', total_amount: 5000, uploaded_at: '2024-01-01' } as never],
    })]
    render(<PaymentList contractId={1} payments={payments} />)
    fireEvent.click(screen.getByTestId('chevron'))
    expect(screen.getByText('inv.pdf')).toBeInTheDocument()
    expect(screen.getByText('#INV-001')).toBeInTheDocument()
  })

  it('collapses invoice rows on second click', () => {
    const payments = [makePayment({
      invoices: [{ id: 1, original_filename: 'inv.pdf', invoice_number: 'INV-001', total_amount: 5000, uploaded_at: '2024-01-01' } as never],
    })]
    render(<PaymentList contractId={1} payments={payments} />)
    fireEvent.click(screen.getByTestId('chevron'))
    expect(screen.getByText('inv.pdf')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('chevron'))
    expect(screen.queryByText('inv.pdf')).not.toBeInTheDocument()
  })

  it('renders invoice without invoice_number', () => {
    const payments = [makePayment({
      invoices: [{ id: 1, original_filename: 'inv.pdf', invoice_number: null, total_amount: null, uploaded_at: null } as never],
    })]
    render(<PaymentList contractId={1} payments={payments} />)
    fireEvent.click(screen.getByTestId('chevron'))
    expect(screen.getByText('inv.pdf')).toBeInTheDocument()
  })

  it('renders invoice with default filename', () => {
    const payments = [makePayment({
      invoices: [{ id: 1, original_filename: null, invoice_number: null, total_amount: null, uploaded_at: null } as never],
    })]
    render(<PaymentList contractId={1} payments={payments} />)
    fireEvent.click(screen.getByTestId('chevron'))
    expect(screen.getByText('发票')).toBeInTheDocument()
  })

  it('renders invoice total_amount as dash when null', () => {
    const payments = [makePayment({
      invoices: [{ id: 1, original_filename: 'inv.pdf', invoice_number: null, total_amount: null, uploaded_at: '2024-01-01' } as never],
    })]
    render(<PaymentList contractId={1} payments={payments} />)
    fireEvent.click(screen.getByTestId('chevron'))
    expect(screen.getAllByText('-').length).toBeGreaterThan(0)
  })

  it('renders empty span when no invoices', () => {
    const payments = [makePayment({ invoices: [] })]
    render(<PaymentList contractId={1} payments={payments} />)
    // No chevron should be rendered
    expect(screen.queryByTestId('chevron')).not.toBeInTheDocument()
  })

  it('handles payment with no note shows dash in table', () => {
    const payments = [makePayment({ note: null, received_at: '2024-01-01' })]
    render(<PaymentList contractId={1} payments={payments} />)
    expect(screen.getByText('-')).toBeInTheDocument()
  })
})
