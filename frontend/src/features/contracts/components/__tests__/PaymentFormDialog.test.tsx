import { render, screen } from '@testing-library/react'
import { PaymentFormDialog } from '../PaymentFormDialog'

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
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
vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) =>
    open ? <div data-testid="dialog">{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('../../types', () => ({
  INVOICE_STATUS_LABELS: {
    UNINVOICED: '未开票',
    PARTIAL: '部分开票',
    INVOICED: '已开票',
  },
}))

describe('PaymentFormDialog', () => {
  it('renders new payment title when no payment', () => {
    render(<PaymentFormDialog open={true} onOpenChange={vi.fn()} contractId={1} onSubmit={vi.fn()} />)
    expect(screen.getByText('新增收款')).toBeInTheDocument()
  })

  it('renders edit title when payment provided', () => {
    const payment = { id: 1, amount: 10000, invoice_status: 'UNINVOICED', invoiced_amount: 0 }
    render(<PaymentFormDialog open={true} onOpenChange={vi.fn()} contractId={1} onSubmit={vi.fn()} payment={payment as never} />)
    expect(screen.getByText('编辑收款')).toBeInTheDocument()
  })

  it('does not render when closed', () => {
    render(<PaymentFormDialog open={false} onOpenChange={vi.fn()} contractId={1} onSubmit={vi.fn()} />)
    expect(screen.queryByTestId('dialog')).not.toBeInTheDocument()
  })

  it('renders save and cancel buttons', () => {
    render(<PaymentFormDialog open={true} onOpenChange={vi.fn()} contractId={1} onSubmit={vi.fn()} />)
    expect(screen.getByText('保存')).toBeInTheDocument()
    expect(screen.getByText('取消')).toBeInTheDocument()
  })

  it('renders amount input label', () => {
    render(<PaymentFormDialog open={true} onOpenChange={vi.fn()} contractId={1} onSubmit={vi.fn()} />)
    expect(screen.getByText('收款金额 *')).toBeInTheDocument()
  })
})
