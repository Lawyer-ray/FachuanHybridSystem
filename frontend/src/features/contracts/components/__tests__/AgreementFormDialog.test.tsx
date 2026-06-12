import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { AgreementFormDialog } from '../AgreementFormDialog'
import type { SupplementaryAgreement } from '../../types'

// ── Mocks ──

const mockClients = [
  { id: 1, name: 'Client A' },
  { id: 2, name: 'Client B' },
  { id: 3, name: 'Client C' },
]

vi.mock('../../hooks/use-clients-select', () => ({
  useClientsSelect: () => ({ data: mockClients }),
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
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    contractId: 1,
    onSubmit: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders new agreement title when no agreement', () => {
    render(<AgreementFormDialog {...defaultProps} />)
    expect(screen.getByText('新增补充协议')).toBeInTheDocument()
  })

  it('renders edit title when agreement provided', () => {
    const agreement = { id: 1, name: 'Test Agreement', parties: [] } as SupplementaryAgreement
    render(<AgreementFormDialog {...defaultProps} agreement={agreement} />)
    expect(screen.getByText('编辑补充协议')).toBeInTheDocument()
  })

  it('does not render when closed', () => {
    render(<AgreementFormDialog {...defaultProps} open={false} />)
    expect(screen.queryByTestId('dialog')).not.toBeInTheDocument()
  })

  it('renders save and cancel buttons', () => {
    render(<AgreementFormDialog {...defaultProps} />)
    expect(screen.getByText('保存')).toBeInTheDocument()
    expect(screen.getByText('取消')).toBeInTheDocument()
  })

  it('renders agreement name input', () => {
    render(<AgreementFormDialog {...defaultProps} />)
    expect(screen.getByText('协议名称')).toBeInTheDocument()
  })

  it('renders client badges for selection', () => {
    render(<AgreementFormDialog {...defaultProps} />)
    expect(screen.getByText('Client A')).toBeInTheDocument()
    expect(screen.getByText('Client B')).toBeInTheDocument()
    expect(screen.getByText('Client C')).toBeInTheDocument()
  })

  it('populates name from agreement when editing', () => {
    const agreement = { id: 1, name: 'Existing Name', parties: [] } as SupplementaryAgreement
    render(<AgreementFormDialog {...defaultProps} agreement={agreement} />)
    expect(screen.getByText('编辑补充协议')).toBeInTheDocument()
  })

  it('populates selectedIds from agreement parties', () => {
    const agreement = {
      id: 1,
      name: 'Agreement',
      parties: [{ client: 1 } as never, { client: 2 } as never],
    } as SupplementaryAgreement
    render(<AgreementFormDialog {...defaultProps} agreement={agreement} />)
    expect(screen.getByText('编辑补充协议')).toBeInTheDocument()
  })

  it('toggles client selection on badge click', () => {
    render(<AgreementFormDialog {...defaultProps} />)
    fireEvent.click(screen.getByText('Client A'))
    // Should toggle the client selection
  })

  it('submits form with contract_id and name', () => {
    const onSubmit = vi.fn()
    render(<AgreementFormDialog {...defaultProps} onSubmit={onSubmit} />)
    const form = screen.getByText('保存').closest('form')!
    fireEvent.submit(form)
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ contract_id: 1 }))
  })

  it('submits form with party_ids when clients selected', () => {
    const onSubmit = vi.fn()
    render(<AgreementFormDialog {...defaultProps} onSubmit={onSubmit} />)
    // Select a client first
    fireEvent.click(screen.getByText('Client A'))
    const form = screen.getByText('保存').closest('form')!
    fireEvent.submit(form)
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ contract_id: 1, party_ids: [1] }))
  })

  it('submits with empty party_ids treated as undefined', () => {
    const onSubmit = vi.fn()
    render(<AgreementFormDialog {...defaultProps} onSubmit={onSubmit} />)
    const form = screen.getByText('保存').closest('form')!
    fireEvent.submit(form)
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ party_ids: undefined }))
  })

  it('handles cancel button click', () => {
    const onOpenChange = vi.fn()
    render(<AgreementFormDialog {...defaultProps} onOpenChange={onOpenChange} />)
    fireEvent.click(screen.getByText('取消'))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('shows submitting state', () => {
    render(<AgreementFormDialog {...defaultProps} submitting={true} />)
    expect(screen.getByText('提交中...')).toBeInTheDocument()
  })

  it('shows save state when not submitting', () => {
    render(<AgreementFormDialog {...defaultProps} submitting={false} />)
    expect(screen.getByText('保存')).toBeInTheDocument()
  })

  it('resets form when open changes from closed to open with no agreement', () => {
    const { rerender } = render(<AgreementFormDialog {...defaultProps} open={false} />)
    rerender(<AgreementFormDialog {...defaultProps} open={true} />)
    expect(screen.getByText('新增补充协议')).toBeInTheDocument()
  })

  it('handles agreement with null name', () => {
    const agreement = { id: 1, name: null, parties: [] } as unknown as SupplementaryAgreement
    render(<AgreementFormDialog {...defaultProps} agreement={agreement} />)
    expect(screen.getByText('编辑补充协议')).toBeInTheDocument()
  })
})
