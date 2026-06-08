import { render, screen } from '@testing-library/react'
import { AgreementFormDialog } from '../components/AgreementFormDialog'

vi.mock('../hooks/use-clients-select', () => ({
  useClientsSelect: () => ({ data: [] }),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))
vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))
vi.mock('@/components/ui/label', () => ({
  Label: ({ children, ...props }: Record<string, unknown>) => <label {...props}>{children}</label>,
}))
vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: Record<string, unknown>) => <span {...props}>{children}</span>,
}))
vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) =>
    open ? <div data-testid="dialog">{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

describe('AgreementFormDialog', () => {
  it('renders new agreement title when no agreement', () => {
    render(<AgreementFormDialog open={true} onOpenChange={vi.fn()} contractId={1} onSubmit={vi.fn()} />)
    expect(screen.getByText('新增补充协议')).toBeInTheDocument()
  })

  it('renders edit title when agreement provided', () => {
    const agreement = { id: 1, name: '补充协议1', parties: [] }
    render(<AgreementFormDialog open={true} onOpenChange={vi.fn()} contractId={1} onSubmit={vi.fn()} agreement={agreement as never} />)
    expect(screen.getByText('编辑补充协议')).toBeInTheDocument()
  })

  it('does not render when closed', () => {
    render(<AgreementFormDialog open={false} onOpenChange={vi.fn()} contractId={1} onSubmit={vi.fn()} />)
    expect(screen.queryByTestId('dialog')).not.toBeInTheDocument()
  })

  it('renders save and cancel buttons', () => {
    render(<AgreementFormDialog open={true} onOpenChange={vi.fn()} contractId={1} onSubmit={vi.fn()} />)
    expect(screen.getByText('保存')).toBeInTheDocument()
    expect(screen.getByText('取消')).toBeInTheDocument()
  })

  it('renders agreement name input', () => {
    render(<AgreementFormDialog open={true} onOpenChange={vi.fn()} contractId={1} onSubmit={vi.fn()} />)
    expect(screen.getByText('协议名称')).toBeInTheDocument()
  })
})
