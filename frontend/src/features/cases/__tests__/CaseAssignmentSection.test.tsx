import { render, screen } from '@testing-library/react'
import { CaseAssignmentSection } from '../components/CaseAssignmentSection'

vi.mock('lucide-react', () => ({
  X: (props: Record<string, unknown>) => <svg data-testid="x-icon" {...props} />,
  Loader2: (props: Record<string, unknown>) => <svg data-testid="loader-icon" {...props} />,
  Search: (props: Record<string, unknown>) => <svg data-testid="search-icon" {...props} />,
  Phone: (props: Record<string, unknown>) => <svg data-testid="phone-icon" {...props} />,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('../hooks/use-assignment-mutations', () => ({
  useAssignmentMutations: () => ({
    createAssignment: { mutate: vi.fn(), isPending: false },
    deleteAssignment: { mutate: vi.fn(), isPending: false },
  }),
}))

vi.mock('@/features/organization/hooks/use-lawyers', () => ({
  useLawyers: () => ({ data: [], isLoading: false }),
}))

vi.mock('@/hooks/use-debounce', () => ({
  useDebounce: (val: string) => val,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: Record<string, unknown>) => <span data-testid="badge" {...props}>{children}</span>,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))

vi.mock('@/components/ui/command', () => ({
  Command: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CommandEmpty: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CommandGroup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CommandInput: (props: Record<string, unknown>) => <input data-testid="command-input" {...props} />,
  CommandItem: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CommandList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/ui/popover', () => ({
  Popover: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

const mockAssignments = [
  {
    id: 1,
    lawyer: 10,
    lawyer_detail: { real_name: '张律师', username: 'zhang', phone: '13900139000' },
  },
  {
    id: 2,
    lawyer: 20,
    lawyer_detail: { real_name: null, username: 'liuser', phone: null },
  },
]

describe('CaseAssignmentSection', () => {
  it('renders empty state when no assignments', () => {
    render(<CaseAssignmentSection assignments={[]} />)
    expect(screen.getByText('暂无指派律师')).toBeInTheDocument()
  })

  it('renders lawyer names', () => {
    render(<CaseAssignmentSection assignments={mockAssignments as never} />)
    expect(screen.getByText('张律师')).toBeInTheDocument()
    expect(screen.getByText('liuser')).toBeInTheDocument()
  })

  it('renders phone when available', () => {
    render(<CaseAssignmentSection assignments={mockAssignments as never} />)
    expect(screen.getByText('13900139000')).toBeInTheDocument()
  })

  it('shows add button when editable with caseId', () => {
    render(<CaseAssignmentSection assignments={[]} caseId={1} editable />)
    expect(screen.getByText('+ 添加')).toBeInTheDocument()
  })

  it('does not show add button when not editable', () => {
    render(<CaseAssignmentSection assignments={[]} caseId={1} />)
    expect(screen.queryByText('+ 添加')).not.toBeInTheDocument()
  })

  it('does not show empty text when editable', () => {
    render(<CaseAssignmentSection assignments={[]} caseId={1} editable />)
    expect(screen.queryByText('暂无指派律师')).not.toBeInTheDocument()
  })
})
