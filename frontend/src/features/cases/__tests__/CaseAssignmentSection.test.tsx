import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { CaseAssignmentSection } from '../components/CaseAssignmentSection'
import { toast } from 'sonner'
import type { CaseAssignment } from '../types'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('lucide-react', () => ({
  X: () => <svg data-testid="x-icon" />,
  Loader2: () => <svg data-testid="loader-icon" />,
  Search: () => <svg data-testid="search-icon" />,
  Phone: () => <svg data-testid="phone-icon" />,
}))

const mockCreateMutate = vi.fn()
const mockDeleteMutate = vi.fn()

vi.mock('../hooks/use-assignment-mutations', () => ({
  useAssignmentMutations: () => ({
    createAssignment: { mutate: mockCreateMutate, isPending: false },
    deleteAssignment: { mutate: mockDeleteMutate, isPending: false },
  }),
}))

vi.mock('@/features/organization/hooks/use-lawyers', () => ({
  useLawyers: vi.fn(() => ({ data: [], isLoading: false })),
}))

vi.mock('@/hooks/use-debounce', () => ({
  useDebounce: (v: string) => v,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, variant, className }: Record<string, unknown>) => <span data-variant={variant} className={className as string}>{children}</span>,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size, className }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} className={className as string}>{children}</button>
  ),
}))

vi.mock('@/components/ui/command', () => ({
  Command: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CommandEmpty: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CommandGroup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CommandInput: ({ placeholder, value, onValueChange }: Record<string, unknown>) => (
    <input placeholder={placeholder as string} value={value as string} onChange={(e) => (onValueChange as (v: string) => void)?.(e.target.value)} />
  ),
  CommandItem: ({ children, onSelect }: { children: React.ReactNode; onSelect?: () => void }) => <div onClick={onSelect}>{children}</div>,
  CommandList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/ui/popover', () => ({
  Popover: ({ children, open }: { children: React.ReactNode; open?: boolean }) => open ? <div>{children}</div> : <div data-testid="popover-closed">{children}</div>,
  PopoverContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

function makeAssignment(overrides: Partial<CaseAssignment> = {}): CaseAssignment {
  return {
    id: 1, case: 1, lawyer: 1,
    lawyer_detail: { id: 1, username: 'lawyer1', real_name: '张律师', phone: '13800138000', is_admin: false, is_active: true, law_firm: null, law_firm_name: null },
    ...overrides,
  }
}

describe('CaseAssignmentSection', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders empty state when not editable', () => {
    render(<CaseAssignmentSection assignments={[]} />)
    expect(screen.getByText('暂无指派律师')).toBeInTheDocument()
  })

  it('does not render empty state when editable', () => {
    render(<CaseAssignmentSection assignments={[]} editable caseId={1} />)
    expect(screen.queryByText('暂无指派律师')).not.toBeInTheDocument()
  })

  it('renders assignment with name', () => {
    render(<CaseAssignmentSection assignments={[makeAssignment()]} />)
    expect(screen.getByText('张律师')).toBeInTheDocument()
  })

  it('renders assignment with phone', () => {
    render(<CaseAssignmentSection assignments={[makeAssignment()]} />)
    expect(screen.getByText('13800138000')).toBeInTheDocument()
  })

  it('renders assignment without phone', () => {
    render(<CaseAssignmentSection assignments={[makeAssignment({
      lawyer_detail: { id: 1, username: 'lawyer1', real_name: '李律师', phone: null, is_admin: false, is_active: true, law_firm: null, law_firm_name: null },
    })]} />)
    expect(screen.getByText('李律师')).toBeInTheDocument()
    expect(screen.queryByTestId('phone-icon')).not.toBeInTheDocument()
  })

  it('renders fallback name when real_name is null', () => {
    render(<CaseAssignmentSection assignments={[makeAssignment({
      lawyer_detail: { id: 1, username: 'user1', real_name: null, phone: null, is_admin: false, is_active: true, law_firm: null, law_firm_name: null },
    })]} />)
    expect(screen.getByText('user1')).toBeInTheDocument()
  })

  it('renders unknown lawyer fallback', () => {
    render(<CaseAssignmentSection assignments={[makeAssignment({
      lawyer_detail: { id: 1, username: null, real_name: null, phone: null, is_admin: false, is_active: true, law_firm: null, law_firm_name: null },
    })]} />)
    expect(screen.getByText('未知律师')).toBeInTheDocument()
  })

  it('renders add button when editable', () => {
    render(<CaseAssignmentSection assignments={[]} editable caseId={1} />)
    expect(screen.getByText('+ 添加')).toBeInTheDocument()
  })

  it('does not render add button when not editable', () => {
    render(<CaseAssignmentSection assignments={[]} />)
    expect(screen.queryByText('+ 添加')).not.toBeInTheDocument()
  })

  it('renders delete button when editable', () => {
    render(<CaseAssignmentSection assignments={[makeAssignment()]} editable caseId={1} />)
    expect(screen.getByTestId('x-icon')).toBeInTheDocument()
  })

  it('calls delete when clicking delete button', () => {
    mockDeleteMutate.mockImplementation((_id: number, opts: { onSuccess: () => void }) => { opts.onSuccess() })
    render(<CaseAssignmentSection assignments={[makeAssignment()]} editable caseId={1} />)
    fireEvent.click(screen.getByTestId('x-icon').closest('button')!)
    expect(mockDeleteMutate).toHaveBeenCalledWith(1, expect.any(Object))
    expect(toast.success).toHaveBeenCalledWith('已删除')
  })

  it('handles delete error', () => {
    mockDeleteMutate.mockImplementation((_id: number, opts: { onError: (e: Error) => void }) => { opts.onError(new Error('Delete failed')) })
    render(<CaseAssignmentSection assignments={[makeAssignment()]} editable caseId={1} />)
    fireEvent.click(screen.getByTestId('x-icon').closest('button')!)
    expect(toast.error).toHaveBeenCalledWith('Delete failed')
  })

  it('does not render delete when not editable', () => {
    render(<CaseAssignmentSection assignments={[makeAssignment()]} />)
    expect(screen.queryByTestId('x-icon')).not.toBeInTheDocument()
  })

  it('renders multiple assignments', () => {
    const assignments = [
      makeAssignment({ id: 1, lawyer_detail: { id: 1, username: 'a', real_name: '律师A', phone: null, is_admin: false, is_active: true, law_firm: null, law_firm_name: null } }),
      makeAssignment({ id: 2, lawyer: 2, lawyer_detail: { id: 2, username: 'b', real_name: '律师B', phone: null, is_admin: false, is_active: true, law_firm: null, law_firm_name: null } }),
    ]
    render(<CaseAssignmentSection assignments={assignments} />)
    expect(screen.getByText('律师A')).toBeInTheDocument()
    expect(screen.getByText('律师B')).toBeInTheDocument()
  })

  it('shows search empty state with search text', () => {
    render(<CaseAssignmentSection assignments={[]} editable caseId={1} />)
    fireEvent.click(screen.getByText('+ 添加'))
    expect(screen.getByText('输入关键词搜索律师')).toBeInTheDocument()
  })
})
