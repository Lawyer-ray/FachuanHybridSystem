import { render, screen, fireEvent, act } from '@testing-library/react'
import { CaseContactSection } from '../components/CaseContactSection'
import { toast } from 'sonner'
import type { CaseContact } from '../types'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('lucide-react', () => ({
  Trash2: () => <svg data-testid="trash-icon" />,
  Loader2: () => <svg data-testid="loader-icon" />,
}))

const mockCreateMutate = vi.fn()
const mockDeleteMutate = vi.fn()

vi.mock('../hooks/use-contact-mutations', () => ({
  useContactMutations: () => ({
    createContact: { mutate: mockCreateMutate, isPending: false },
    deleteContact: { mutate: mockDeleteMutate, isPending: false },
  }),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size, className }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} className={className as string}>{children}</button>
  ),
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children, onValueChange }: { children: React.ReactNode; onValueChange?: (v: string) => void }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value }: { children: React.ReactNode; value: string }) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: ({ placeholder }: { placeholder?: string }) => <span>{placeholder}</span>,
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
  AlertDialogContent: ({ children, size }: { children: React.ReactNode; size?: string }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  AlertDialogTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

function makeContact(overrides: Partial<CaseContact> = {}): CaseContact {
  return {
    id: 1, case_id: 1, authority_id: null, authority_name: null,
    name: '张法官', role: 'judge', role_display: '法官',
    phone: '13800138000', address: '北京市朝阳区', stage: null, stage_display: null,
    note: '备注信息', created_at: '2025-06-01', updated_at: '2025-06-01', ...overrides,
  }
}

describe('CaseContactSection', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders empty state', () => {
    render(<CaseContactSection contacts={[]} />)
    expect(screen.getByText('暂无工作人员信息')).toBeInTheDocument()
  })

  it('renders contact name and role', () => {
    render(<CaseContactSection contacts={[makeContact()]} />)
    expect(screen.getByText('张法官')).toBeInTheDocument()
    expect(screen.getByText('法官')).toBeInTheDocument()
  })

  it('renders contact phone', () => {
    render(<CaseContactSection contacts={[makeContact()]} />)
    expect(screen.getByText('13800138000')).toBeInTheDocument()
  })

  it('renders contact address', () => {
    render(<CaseContactSection contacts={[makeContact()]} />)
    expect(screen.getByText('北京市朝阳区')).toBeInTheDocument()
  })

  it('renders contact note', () => {
    render(<CaseContactSection contacts={[makeContact()]} />)
    expect(screen.getByText('备注信息')).toBeInTheDocument()
  })

  it('renders contact without phone', () => {
    const contact = makeContact({ phone: null })
    render(<CaseContactSection contacts={[contact]} />)
    expect(screen.getByText('张法官')).toBeInTheDocument()
    expect(screen.queryByText('13800138000')).not.toBeInTheDocument()
  })

  it('renders contact with stage', () => {
    const contact = makeContact({ stage: 'first_trial' })
    render(<CaseContactSection contacts={[contact]} />)
    expect(screen.getByText(/一审/)).toBeInTheDocument()
  })

  it('renders contact with authority_name', () => {
    const contact = makeContact({ authority_name: '最高人民法院' })
    render(<CaseContactSection contacts={[contact]} />)
    expect(screen.getByText('最高人民法院')).toBeInTheDocument()
  })

  it('renders contact with role fallback when no role_display', () => {
    const contact = makeContact({ role_display: null })
    render(<CaseContactSection contacts={[contact]} />)
    expect(screen.getByText('judge')).toBeInTheDocument()
  })

  it('renders delete button when editable', () => {
    render(<CaseContactSection contacts={[makeContact()]} editable caseId={1} />)
    expect(screen.getByTestId('trash-icon')).toBeInTheDocument()
  })

  it('does not render delete button when not editable', () => {
    render(<CaseContactSection contacts={[makeContact()]} />)
    expect(screen.queryByTestId('trash-icon')).not.toBeInTheDocument()
  })

  it('handles delete success', () => {
    mockDeleteMutate.mockImplementation((_id: number, opts: { onSuccess: () => void }) => { opts.onSuccess() })
    render(<CaseContactSection contacts={[makeContact()]} editable caseId={1} />)
    fireEvent.click(screen.getByText('删除'))
    expect(toast.success).toHaveBeenCalledWith('已删除')
  })

  it('handles delete error', () => {
    mockDeleteMutate.mockImplementation((_id: number, opts: { onError: () => void }) => { opts.onError() })
    render(<CaseContactSection contacts={[makeContact()]} editable caseId={1} />)
    fireEvent.click(screen.getByText('删除'))
    expect(toast.error).toHaveBeenCalledWith('删除失败')
  })

  it('handles contact click callback', () => {
    const onClick = vi.fn()
    render(<CaseContactSection contacts={[makeContact()]} onContactClick={onClick} />)
    fireEvent.click(screen.getByText('张法官'))
    expect(onClick).toHaveBeenCalledWith(makeContact())
  })

  it('renders with ref', () => {
    const ref = { current: null as any }
    render(<CaseContactSection contacts={[]} editable caseId={1} ref={ref} />)
    expect(ref.current).toBeTruthy()
    expect(typeof ref.current.openDialog).toBe('function')
  })

  it('opens dialog via ref', () => {
    const ref = { current: null as any }
    render(<CaseContactSection contacts={[]} editable caseId={1} ref={ref} />)
    act(() => { ref.current.openDialog() })
    expect(screen.getByTestId('dialog')).toBeInTheDocument()
    expect(screen.getByText('添加工作人员')).toBeInTheDocument()
  })

  it('handles add with empty form', () => {
    const ref = { current: null as any }
    render(<CaseContactSection contacts={[]} editable caseId={1} ref={ref} />)
    act(() => { ref.current.openDialog() })
    fireEvent.click(screen.getByText('保存'))
    expect(mockCreateMutate).not.toHaveBeenCalled()
  })

  it('renders multiple contacts', () => {
    const contacts = [
      makeContact({ id: 1, name: '张法官', role: 'judge' }),
      makeContact({ id: 2, name: '李书记', role: 'clerk', role_display: '书记员' }),
    ]
    render(<CaseContactSection contacts={contacts} />)
    expect(screen.getByText('张法官')).toBeInTheDocument()
    expect(screen.getByText('李书记')).toBeInTheDocument()
  })

  it('renders contact with unknown stage fallback', () => {
    const contact = makeContact({ stage: 'unknown_stage' })
    render(<CaseContactSection contacts={[contact]} />)
    expect(screen.getByText(/unknown_stage/)).toBeInTheDocument()
  })

  it('renders contact without address', () => {
    const contact = makeContact({ address: null })
    render(<CaseContactSection contacts={[contact]} />)
    expect(screen.getByText('张法官')).toBeInTheDocument()
  })

  it('renders contact without note', () => {
    const contact = makeContact({ note: null })
    render(<CaseContactSection contacts={[contact]} />)
    expect(screen.getByText('张法官')).toBeInTheDocument()
  })
})
