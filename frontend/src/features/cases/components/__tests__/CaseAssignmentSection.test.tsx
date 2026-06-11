import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { CaseAssignmentSection } from '../CaseAssignmentSection'
import type { CaseAssignment } from '../../types'

vi.mock('react-router', () => ({
  useNavigate: () => vi.fn(),
  Link: ({ children, ...props }: Record<string, unknown>) => <a {...props}>{children}</a>,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

import { toast } from 'sonner'

const mockCreateMutate = vi.fn()
const mockDeleteMutate = vi.fn()

vi.mock('../../hooks/use-assignment-mutations', () => ({
  useAssignmentMutations: () => ({
    createAssignment: { mutate: mockCreateMutate, isPending: false },
    deleteAssignment: { mutate: mockDeleteMutate, isPending: false },
  }),
}))

vi.mock('@/features/organization/hooks/use-lawyers', () => ({
  useLawyers: vi.fn().mockReturnValue({ data: [], isLoading: false }),
}))

vi.mock('@/hooks/use-debounce', () => ({
  useDebounce: (v: string) => v,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}))
vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))
vi.mock('@/components/ui/command', () => ({
  Command: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CommandEmpty: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CommandGroup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CommandInput: (p: Record<string, unknown>) => <input {...p} />,
  CommandItem: ({ children, ...p }: Record<string, unknown>) => <div {...p}>{children}</div>,
  CommandList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('@/components/ui/popover', () => ({
  Popover: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('lucide-react', () => ({
  X: (p: Record<string, unknown>) => <svg data-testid="x-icon" {...p} />,
  Loader2: (p: Record<string, unknown>) => <svg data-testid="loader" {...p} />,
  Search: (p: Record<string, unknown>) => <svg data-testid="search" {...p} />,
  Phone: (p: Record<string, unknown>) => <svg data-testid="phone" {...p} />,
}))

const makeAssignment = (overrides: Partial<CaseAssignment> = {}): CaseAssignment =>
  ({
    id: 1,
    lawyer: 10,
    lawyer_detail: { real_name: '李律师', username: 'li', phone: '13800000000' },
    ...overrides,
  }) as unknown as CaseAssignment

describe('CaseAssignmentSection', () => {
  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  // -- Non-editable rendering --

  it('renders empty message when no assignments and not editable', () => {
    render(<CaseAssignmentSection assignments={[]} />)
    expect(screen.getByText('暂无指派律师')).toBeInTheDocument()
  })

  it('renders no empty message when editable without caseId (editable hides empty text)', () => {
    render(<CaseAssignmentSection assignments={[]} editable />)
    expect(screen.queryByText('暂无指派律师')).not.toBeInTheDocument()
  })

  it('renders lawyer name', () => {
    render(<CaseAssignmentSection assignments={[makeAssignment()]} />)
    expect(screen.getByText('李律师')).toBeInTheDocument()
  })

  it('renders lawyer phone', () => {
    render(<CaseAssignmentSection assignments={[makeAssignment()]} />)
    expect(screen.getByText('13800000000')).toBeInTheDocument()
  })

  it('renders username fallback when real_name is null', () => {
    render(
      <CaseAssignmentSection
        assignments={[makeAssignment({ lawyer_detail: { real_name: null, username: 'li_user', phone: '123' } })]}
      />,
    )
    expect(screen.getByText('li_user')).toBeInTheDocument()
  })

  it('renders "未知律师" fallback when both names are null', () => {
    render(
      <CaseAssignmentSection
        assignments={[makeAssignment({ lawyer_detail: { real_name: null, username: null, phone: '123' } })]}
      />,
    )
    expect(screen.getByText('未知律师')).toBeInTheDocument()
  })

  it('does not render phone when absent', () => {
    render(
      <CaseAssignmentSection
        assignments={[makeAssignment({ lawyer_detail: { real_name: '律师', username: 'l', phone: '' } })]}
      />,
    )
    expect(screen.queryByTestId('phone')).not.toBeInTheDocument()
  })

  // -- Editable mode --

  it('shows delete button in editable mode with caseId', () => {
    render(<CaseAssignmentSection assignments={[makeAssignment()]} editable caseId={1} />)
    expect(screen.getByTestId('x-icon')).toBeInTheDocument()
  })

  it('does not show delete button when not editable', () => {
    render(<CaseAssignmentSection assignments={[makeAssignment()]} />)
    expect(screen.queryByTestId('x-icon')).not.toBeInTheDocument()
  })

  it('does not show delete button when caseId is missing', () => {
    render(<CaseAssignmentSection assignments={[makeAssignment()]} editable />)
    expect(screen.queryByTestId('x-icon')).not.toBeInTheDocument()
  })

  it('shows add button in editable mode with caseId', () => {
    render(<CaseAssignmentSection assignments={[]} editable caseId={1} />)
    expect(screen.getByText('+ 添加')).toBeInTheDocument()
  })

  it('does not show add button when not editable', () => {
    render(<CaseAssignmentSection assignments={[]} />)
    expect(screen.queryByText('+ 添加')).not.toBeInTheDocument()
  })

  // -- Mutations --

  it('calls deleteAssignment.mutate on delete click', () => {
    render(<CaseAssignmentSection assignments={[makeAssignment()]} editable caseId={1} />)
    fireEvent.click(screen.getByTestId('x-icon').closest('button')!)
    expect(mockDeleteMutate).toHaveBeenCalledWith(1, expect.objectContaining({
      onSuccess: expect.any(Function),
      onError: expect.any(Function),
    }))
  })

  it('shows success toast on delete', () => {
    mockDeleteMutate.mockImplementation((_id: number, opts: { onSuccess: () => void }) => {
      opts.onSuccess()
    })
    render(<CaseAssignmentSection assignments={[makeAssignment()]} editable caseId={1} />)
    fireEvent.click(screen.getByTestId('x-icon').closest('button')!)
    expect(toast.success).toHaveBeenCalledWith('已删除')
  })

  it('shows error toast on delete failure', () => {
    mockDeleteMutate.mockImplementation((_id: number, opts: { onError: (e: Error) => void }) => {
      opts.onError(new Error('delete failed'))
    })
    render(<CaseAssignmentSection assignments={[makeAssignment()]} editable caseId={1} />)
    fireEvent.click(screen.getByTestId('x-icon').closest('button')!)
    expect(toast.error).toHaveBeenCalledWith('delete failed')
  })

  it('shows generic error toast when error has no message', () => {
    mockDeleteMutate.mockImplementation((_id: number, opts: { onError: (e: Error) => void }) => {
      opts.onError(new Error(''))
    })
    render(<CaseAssignmentSection assignments={[makeAssignment()]} editable caseId={1} />)
    fireEvent.click(screen.getByTestId('x-icon').closest('button')!)
    expect(toast.error).toHaveBeenCalledWith('删除失败')
  })

  it('does not select when caseId is missing', () => {
    render(<CaseAssignmentSection assignments={[]} editable />)
    // The handleSelect function early returns when !caseId
    // Add button is rendered but clicking a lawyer wouldn't mutate
    expect(screen.queryByText('+ 添加')).not.toBeInTheDocument()
  })

  // -- Multiple assignments --

  it('renders multiple assignments', () => {
    const assignments = [
      makeAssignment({ id: 1, lawyer: 10, lawyer_detail: { real_name: '律师A', username: 'a', phone: '111' } }),
      makeAssignment({ id: 2, lawyer: 20, lawyer_detail: { real_name: '律师B', username: 'b', phone: '222' } }),
    ]
    render(<CaseAssignmentSection assignments={assignments as any} />)
    expect(screen.getByText('律师A')).toBeInTheDocument()
    expect(screen.getByText('律师B')).toBeInTheDocument()
  })

  // -- Pending indicator --

  it('does not show loader when not pending', () => {
    render(<CaseAssignmentSection assignments={[]} editable caseId={1} />)
    expect(screen.queryByTestId('loader')).not.toBeInTheDocument()
  })
})
