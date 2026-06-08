import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { CaseAccessGrantSection } from '../components/CaseAccessGrantSection'
import { toast } from 'sonner'
import type { CaseAccessGrant } from '../types'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('lucide-react', () => ({
  UserPlus: () => <svg data-testid="user-plus-icon" />,
  Trash2: () => <svg data-testid="trash-icon" />,
  Loader2: () => <svg data-testid="loader-icon" />,
  ShieldCheck: () => <svg data-testid="shield-check-icon" />,
}))

const mockCreateMutate = vi.fn()
const mockDeleteMutate = vi.fn()

vi.mock('../hooks/use-access-grant-mutations', () => ({
  useAccessGrantMutations: () => ({
    createGrant: { mutate: mockCreateMutate, isPending: false },
    deleteGrant: { mutate: mockDeleteMutate, isPending: false },
  }),
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, className }: Record<string, unknown>) => <div className={className as string}>{children}</div>,
  CardHeader: ({ children, className }: Record<string, unknown>) => <div className={className as string}>{children}</div>,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean}>{children}</button>
  ),
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

vi.mock('@/components/ui/label', () => ({
  Label: ({ children }: { children: React.ReactNode }) => <label>{children}</label>,
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) => open ? <div data-testid="dialog">{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogAction: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => <button onClick={onClick}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  AlertDialogTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

function makeGrant(overrides: Partial<CaseAccessGrant> = {}): CaseAccessGrant {
  return {
    id: 1, case: 1, grantee: 2,
    grantee_detail: { id: 2, username: 'lawyer2', real_name: '李律师', phone: '13900139000', is_admin: false, is_active: true, law_firm: null, law_firm_name: null }, // pragma: allowlist secret
    created_at: '2025-01-01', ...overrides,
  }
}

describe('CaseAccessGrantSection', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders empty state when no grants', () => {
    render(<CaseAccessGrantSection grants={[]} />)
    expect(screen.getByText('暂无额外授权')).toBeInTheDocument()
    expect(screen.getByTestId('shield-check-icon')).toBeInTheDocument()
  })

  it('renders grant with name', () => {
    render(<CaseAccessGrantSection grants={[makeGrant()]} />)
    expect(screen.getByText('李律师')).toBeInTheDocument()
  })

  it('renders grant with phone', () => {
    render(<CaseAccessGrantSection grants={[makeGrant()]} />)
    expect(screen.getByText('13900139000')).toBeInTheDocument() // pragma: allowlist secret
  })

  it('renders grant without phone', () => {
    const grant = makeGrant({
      grantee_detail: { id: 2, username: 'lawyer2', real_name: '王律师', phone: null, is_admin: false, is_active: true, law_firm: null, law_firm_name: null },
    })
    render(<CaseAccessGrantSection grants={[grant]} />)
    expect(screen.getByText('王律师')).toBeInTheDocument()
  })

  it('renders fallback name when real_name is null', () => {
    const grant = makeGrant({
      grantee_detail: { id: 2, username: 'user2', real_name: null, phone: null, is_admin: false, is_active: true, law_firm: null, law_firm_name: null },
    })
    render(<CaseAccessGrantSection grants={[grant]} />)
    expect(screen.getByText('user2')).toBeInTheDocument()
  })

  it('renders unknown lawyer fallback', () => {
    const grant = makeGrant({
      grantee_detail: { id: 2, username: null, real_name: null, phone: null, is_admin: false, is_active: true, law_firm: null, law_firm_name: null },
    })
    render(<CaseAccessGrantSection grants={[grant]} />)
    expect(screen.getByText('未知律师')).toBeInTheDocument()
  })

  it('renders add button when editable', () => {
    render(<CaseAccessGrantSection grants={[]} editable caseId={1} />)
    expect(screen.getByText('添加授权')).toBeInTheDocument()
  })

  it('does not render add button when not editable', () => {
    render(<CaseAccessGrantSection grants={[]} />)
    expect(screen.queryByText('添加授权')).not.toBeInTheDocument()
  })

  it('opens dialog when clicking add', () => {
    render(<CaseAccessGrantSection grants={[]} editable caseId={1} />)
    fireEvent.click(screen.getByText('添加授权'))
    expect(screen.getByTestId('dialog')).toBeInTheDocument()
    expect(screen.getByText('授权律师查看案件')).toBeInTheDocument()
  })

  it('handles add with empty grantee ID', () => {
    render(<CaseAccessGrantSection grants={[]} editable caseId={1} />)
    fireEvent.click(screen.getByText('添加授权'))
    fireEvent.click(screen.getByText('确认授权'))
    // Should not call mutate since granteeId is empty
    expect(mockCreateMutate).not.toHaveBeenCalled()
  })

  it('handles add with invalid grantee ID', () => {
    render(<CaseAccessGrantSection grants={[]} editable caseId={1} />)
    fireEvent.click(screen.getByText('添加授权'))
    const input = screen.getByPlaceholderText('输入律师 ID')
    // Set to non-numeric value
    fireEvent.change(input, { target: { value: 'abc' } })
    fireEvent.click(screen.getByText('确认授权'))
    // The handleAdd function should either show error or not call mutate
    expect(mockCreateMutate).not.toHaveBeenCalled()
  })

  it('handles add with valid grantee ID', () => {
    mockCreateMutate.mockImplementation((_data: unknown, opts: { onSuccess: () => void }) => { opts.onSuccess() })
    render(<CaseAccessGrantSection grants={[]} editable caseId={1} />)
    fireEvent.click(screen.getByText('添加授权'))
    const input = screen.getByPlaceholderText('输入律师 ID')
    fireEvent.change(input, { target: { value: '5' } })
    fireEvent.click(screen.getByText('确认授权'))
    expect(mockCreateMutate).toHaveBeenCalledWith(
      { case_id: 1, grantee_id: 5 },
      expect.any(Object),
    )
    expect(toast.success).toHaveBeenCalledWith('授权成功')
  })

  it('handles add error', () => {
    mockCreateMutate.mockImplementation((_data: unknown, opts: { onError: (e: Error) => void }) => { opts.onError(new Error('Failed')) })
    render(<CaseAccessGrantSection grants={[]} editable caseId={1} />)
    fireEvent.click(screen.getByText('添加授权'))
    const input = screen.getByPlaceholderText('输入律师 ID')
    fireEvent.change(input, { target: { value: '5' } })
    fireEvent.click(screen.getByText('确认授权'))
    expect(toast.error).toHaveBeenCalledWith('Failed')
  })

  it('does not show add button without caseId', () => {
    render(<CaseAccessGrantSection grants={[]} editable />)
    expect(screen.queryByText('添加授权')).not.toBeInTheDocument()
  })

  it('renders delete button when editable', () => {
    render(<CaseAccessGrantSection grants={[makeGrant()]} editable caseId={1} />)
    expect(screen.getByTestId('trash-icon')).toBeInTheDocument()
  })

  it('does not render delete button when not editable', () => {
    render(<CaseAccessGrantSection grants={[makeGrant()]} />)
    expect(screen.queryByTestId('trash-icon')).not.toBeInTheDocument()
  })

  it('handles delete success', () => {
    mockDeleteMutate.mockImplementation((_id: number, opts: { onSuccess: () => void }) => { opts.onSuccess() })
    render(<CaseAccessGrantSection grants={[makeGrant()]} editable caseId={1} />)
    fireEvent.click(screen.getByText('撤销'))
    expect(toast.success).toHaveBeenCalledWith('已撤销授权')
  })

  it('handles delete error', () => {
    mockDeleteMutate.mockImplementation((_id: number, opts: { onError: (e: Error) => void }) => { opts.onError(new Error('Revoke failed')) })
    render(<CaseAccessGrantSection grants={[makeGrant()]} editable caseId={1} />)
    fireEvent.click(screen.getByText('撤销'))
    expect(toast.error).toHaveBeenCalledWith('Revoke failed')
  })

  it('renders multiple grants', () => {
    const grants = [
      makeGrant({ id: 1, grantee_detail: { id: 2, username: 'a', real_name: '律师A', phone: null, is_admin: false, is_active: true, law_firm: null, law_firm_name: null } }),
      makeGrant({ id: 2, grantee: 3, grantee_detail: { id: 3, username: 'b', real_name: '律师B', phone: null, is_admin: false, is_active: true, law_firm: null, law_firm_name: null } }),
    ]
    render(<CaseAccessGrantSection grants={grants} />)
    expect(screen.getByText('律师A')).toBeInTheDocument()
    expect(screen.getByText('律师B')).toBeInTheDocument()
  })

  it('renders shield check icon for each grant', () => {
    render(<CaseAccessGrantSection grants={[makeGrant()]} />)
    const icons = screen.getAllByTestId('shield-check-icon')
    expect(icons.length).toBeGreaterThanOrEqual(1)
  })
})
