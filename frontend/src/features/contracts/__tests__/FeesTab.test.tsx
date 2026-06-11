import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { FeesTab } from '../components/FeesTab'
import { contractApi } from '../api'
import type { Contract } from '../types'

// ── Mocks ──

vi.mock('lucide-react', () => ({
  Trash2: (p: Record<string, unknown>) => <svg data-testid="trash" {...p} />,
  Image: (p: Record<string, unknown>) => <svg data-testid="image" {...p} />,
  DollarSign: (p: Record<string, unknown>) => <svg data-testid="dollar" {...p} />,
  Receipt: (p: Record<string, unknown>) => <svg data-testid="receipt" {...p} />,
  Plus: (p: Record<string, unknown>) => <svg data-testid="plus" {...p} />,
  Edit: (p: Record<string, unknown>) => <svg data-testid="edit" {...p} />,
  ChevronRight: (p: Record<string, unknown>) => <svg data-testid="chevron" {...p} />,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('../api', () => ({
  contractApi: {
    deleteClientPaymentRecord: vi.fn(),
  },
}))

vi.mock('@/lib/api', () => ({
  resolveMediaUrl: (path: string) => `https://cdn.example.com/${path}`,
}))

vi.mock('@/lib/format', () => ({
  formatAmountInt: (val: number) => `¥${val.toLocaleString()}`,
  formatAmount: (val: number) => `¥${val.toLocaleString()}`,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: Record<string, unknown>) => <span {...props}>{children}</span>,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
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

vi.mock('@/components/ui/table', () => ({
  Table: ({ children }: { children: React.ReactNode }) => <table>{children}</table>,
  TableBody: ({ children }: { children: React.ReactNode }) => <tbody>{children}</tbody>,
  TableCell: ({ children, ...props }: Record<string, unknown>) => <td {...props}>{children}</td>,
  TableHead: ({ children, ...props }: Record<string, unknown>) => <th {...props}>{children}</th>,
  TableHeader: ({ children }: { children: React.ReactNode }) => <thead>{children}</thead>,
  TableRow: ({ children }: { children: React.ReactNode }) => <tr>{children}</tr>,
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardHeader: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardTitle: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) =>
    open ? <div data-testid="dialog">{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

vi.mock('@/components/ui/label', () => ({
  Label: ({ children, ...props }: Record<string, unknown>) => <label {...props}>{children}</label>,
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => <span />,
}))

vi.mock('@/components/shared', () => ({
  DetailField: ({ label, value }: { label: string; value: unknown }) => (
    <div data-testid={`field-${label}`}>
      <span>{label}</span>
      {value != null && typeof value !== 'object' ? <span>{String(value)}</span> : value as React.ReactNode}
    </div>
  ),
  DetailCard: ({ title, children, extra }: { title: string; children: React.ReactNode; extra?: React.ReactNode }) => (
    <div data-testid={`card-${title}`}>
      <div>{title}</div>
      {extra}
      {children}
    </div>
  ),
}))

vi.mock('../components/PaymentList', () => ({
  PaymentList: ({ payments }: { payments: unknown[] }) => <div data-testid="payment-list">{payments.length} payments</div>,
}))

// ── Helpers ──

function makeContract(overrides: Partial<Contract> = {}): Contract {
  return {
    id: 1,
    name: 'Test',
    fee_mode: 'FIXED',
    fixed_amount: 100000,
    risk_rate: null,
    custom_terms: null,
    total_received: 50000,
    total_invoiced: 30000,
    unpaid_amount: 50000,
    payments: [],
    invoices: [],
    client_payment_records: [],
    ...overrides,
  } as unknown as Contract
}

describe('FeesTab', () => {
  beforeEach(() => {
    vi.mocked(contractApi.deleteClientPaymentRecord).mockResolvedValue(undefined as never)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('renders fee terms card', () => {
    render(<FeesTab contract={makeContract()} />)
    expect(screen.getByText('收费条款')).toBeInTheDocument()
  })

  it('renders fee mode label', () => {
    render(<FeesTab contract={makeContract()} />)
    expect(screen.getByText('固定收费')).toBeInTheDocument()
  })

  it('falls back to raw fee_mode for unknown mode', () => {
    render(<FeesTab contract={makeContract({ fee_mode: 'UNKNOWN' })} />)
    expect(screen.getByText('UNKNOWN')).toBeInTheDocument()
  })

  it('renders fixed amount when set', () => {
    render(<FeesTab contract={makeContract({ fixed_amount: 100000 })} />)
    expect(screen.getByText('固定/前期律师费')).toBeInTheDocument()
  })

  it('hides fixed amount when null', () => {
    render(<FeesTab contract={makeContract({ fixed_amount: null })} />)
    expect(screen.queryByText('固定/前期律师费')).not.toBeInTheDocument()
  })

  it('renders risk rate when set', () => {
    render(<FeesTab contract={makeContract({ risk_rate: 15 })} />)
    expect(screen.getByText('15%')).toBeInTheDocument()
  })

  it('hides risk rate when null', () => {
    render(<FeesTab contract={makeContract({ risk_rate: null })} />)
    expect(screen.queryByText('风险比例')).not.toBeInTheDocument()
  })

  it('renders custom terms when set', () => {
    render(<FeesTab contract={makeContract({ custom_terms: 'Custom' })} />)
    expect(screen.getByText('Custom')).toBeInTheDocument()
  })

  it('hides custom terms when null', () => {
    render(<FeesTab contract={makeContract({ custom_terms: null })} />)
    expect(screen.queryByText('自定义条款')).not.toBeInTheDocument()
  })

  it('renders collection progress', () => {
    render(<FeesTab contract={makeContract()} />)
    expect(screen.getAllByText('收款进度').length).toBeGreaterThan(0)
  })

  it('calculates payment percent correctly', () => {
    render(<FeesTab contract={makeContract({ fixed_amount: 100000, total_received: 50000 })} />)
    expect(screen.getByText('50%')).toBeInTheDocument()
  })

  it('shows "已收齐" when payment >= 100%', () => {
    render(<FeesTab contract={makeContract({ fixed_amount: 100000, total_received: 100000 })} />)
    expect(screen.getByText('已收齐')).toBeInTheDocument()
  })

  it('shows unpaid amount when > 0', () => {
    render(<FeesTab contract={makeContract({ unpaid_amount: 50000 })} />)
    expect(screen.getByText(/未收/)).toBeInTheDocument()
  })

  it('hides unpaid amount when null', () => {
    render(<FeesTab contract={makeContract({ unpaid_amount: null })} />)
    expect(screen.queryByText(/未收/)).not.toBeInTheDocument()
  })

  it('hides unpaid amount when 0', () => {
    render(<FeesTab contract={makeContract({ unpaid_amount: 0 })} />)
    expect(screen.queryByText(/未收/)).not.toBeInTheDocument()
  })

  it('shows dash when no fixed amount for receivable', () => {
    render(<FeesTab contract={makeContract({ fixed_amount: null, total_received: 0 })} />)
    expect(screen.getByText('应收 —')).toBeInTheDocument()
  })

  it('renders invoice progress', () => {
    render(<FeesTab contract={makeContract()} />)
    expect(screen.getByText('开票进度')).toBeInTheDocument()
  })

  it('calculates invoice percent correctly', () => {
    render(<FeesTab contract={makeContract({ total_received: 100000, total_invoiced: 50000 })} />)
    expect(screen.getByText('50%')).toBeInTheDocument()
  })

  it('shows "待开票" when invoice < 100% and received > 0', () => {
    render(<FeesTab contract={makeContract({ total_received: 100000, total_invoiced: 50000 })} />)
    expect(screen.getByText('待开票')).toBeInTheDocument()
  })

  it('hides "待开票" when invoice >= 100%', () => {
    render(<FeesTab contract={makeContract({ total_received: 100000, total_invoiced: 100000 })} />)
    expect(screen.queryByText('待开票')).not.toBeInTheDocument()
  })

  it('hides "待开票" when received = 0', () => {
    render(<FeesTab contract={makeContract({ total_received: 0, total_invoiced: 0 })} />)
    expect(screen.queryByText('待开票')).not.toBeInTheDocument()
  })

  it('renders PaymentList component', () => {
    render(<FeesTab contract={makeContract()} />)
    expect(screen.getByTestId('payment-list')).toBeInTheDocument()
  })

  it('renders invoice section with invoices', () => {
    const contract = makeContract({
      payments: [
        {
          id: 1,
          amount: 10000,
          invoices: [{ id: 1, original_filename: 'inv.pdf', invoice_number: 'INV-001', total_amount: 10000, uploaded_at: '2024-01-01' }],
        } as never,
      ],
    })
    render(<FeesTab contract={contract} />)
    expect(screen.getByText('发票记录')).toBeInTheDocument()
    expect(screen.getByText('inv.pdf')).toBeInTheDocument()
    expect(screen.getByText('#INV-001')).toBeInTheDocument()
  })

  it('hides invoice section when no invoices', () => {
    render(<FeesTab contract={makeContract({ payments: [] })} />)
    expect(screen.queryByText('发票记录')).not.toBeInTheDocument()
  })

  it('renders invoices without invoice_number', () => {
    const contract = makeContract({
      payments: [
        {
          id: 1,
          amount: 10000,
          invoices: [{ id: 1, original_filename: 'inv.pdf', invoice_number: null, total_amount: null, uploaded_at: null }],
        } as never,
      ],
    })
    render(<FeesTab contract={contract} />)
    expect(screen.getByText('发票记录')).toBeInTheDocument()
  })

  it('renders client payment records section', () => {
    render(<FeesTab contract={makeContract()} />)
    expect(screen.getByText('客户付款凭证')).toBeInTheDocument()
  })

  it('renders empty client payment records', () => {
    render(<FeesTab contract={makeContract({ client_payment_records: [] })} />)
    expect(screen.getByText('暂无客户付款凭证')).toBeInTheDocument()
  })

  it('renders client payment records with data', () => {
    const contract = makeContract({
      client_payment_records: [
        { id: 1, amount: 5000, note: 'Payment 1', created_at: '2024-01-01', image_path: '/img/1.jpg' },
        { id: 2, amount: 3000, note: null, created_at: '2024-02-01', image_path: null },
      ] as never,
    })
    render(<FeesTab contract={contract} />)
    expect(screen.getByText('2 笔 · ¥8,000')).toBeInTheDocument()
  })

  it('handles delete client payment record', async () => {
    const contract = makeContract({
      client_payment_records: [
        { id: 1, amount: 5000, note: '', created_at: '2024-01-01', image_path: null },
      ] as never,
    })
    render(<FeesTab contract={contract} />)
    // Click delete button
    const deleteBtn = screen.getByTestId('trash').closest('button')!
    fireEvent.click(deleteBtn)
    // Confirm dialog should appear
    await waitFor(() => expect(screen.getByTestId('alert-dialog')).toBeInTheDocument())
  })

  it('renders invoice with uploaded_at', () => {
    const contract = makeContract({
      payments: [
        {
          id: 1,
          amount: 10000,
          invoices: [{ id: 1, original_filename: 'inv.pdf', invoice_number: null, total_amount: 5000, uploaded_at: '2024-06-01' }],
        } as never,
      ],
    })
    render(<FeesTab contract={contract} />)
    expect(screen.getByText('发票记录')).toBeInTheDocument()
  })

  it('renders client payment with image_path link', () => {
    const contract = makeContract({
      client_payment_records: [
        { id: 1, amount: 1000, note: '', created_at: '2024-01-01', image_path: '/img/receipt.jpg' },
      ] as never,
    })
    render(<FeesTab contract={contract} />)
    expect(screen.getByTestId('image')).toBeInTheDocument()
  })

  it('renders payment percent capped at 100', () => {
    render(<FeesTab contract={makeContract({ fixed_amount: 100, total_received: 200 })} />)
    expect(screen.getAllByText('100%').length).toBeGreaterThan(0)
  })
})
