import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { CasePartySection } from '../components/CasePartySection'

vi.mock('lucide-react', () => ({
  X: (props: Record<string, unknown>) => <svg data-testid="x-icon" {...props} />,
  Loader2: (props: Record<string, unknown>) => <svg data-testid="loader-icon" {...props} />,
  Search: (props: Record<string, unknown>) => <svg data-testid="search-icon" {...props} />,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('../hooks/use-party-mutations', () => ({
  usePartyMutations: () => ({
    createParty: { mutate: vi.fn(), isPending: false },
    deleteParty: { mutate: vi.fn(), isPending: false },
  }),
}))

vi.mock('@/features/contracts/hooks/use-clients-select', () => ({
  useClientsSelect: () => ({ data: [] }),
}))

vi.mock('@/routes/paths', () => ({
  generatePath: { clientDetail: (id: number) => `/admin/clients/${id}` },
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

vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => <span />,
}))

const mockParties = [
  {
    id: 1,
    client: 10,
    legal_status: 'plaintiff',
    client_detail: { name: '张三', is_our_client: true, client_type_label: '个人' },
  },
  {
    id: 2,
    client: 20,
    legal_status: null,
    client_detail: { name: '李四', is_our_client: false, client_type_label: '企业' },
  },
]

describe('CasePartySection', () => {
  it('renders empty state when no parties and not editable', () => {
    render(<MemoryRouter><CasePartySection parties={[]} /></MemoryRouter>)
    expect(screen.getByText('暂无当事人')).toBeInTheDocument()
  })

  it('renders party names', () => {
    render(<MemoryRouter><CasePartySection parties={mockParties as never} /></MemoryRouter>)
    expect(screen.getByText('张三')).toBeInTheDocument()
    expect(screen.getByText('李四')).toBeInTheDocument()
  })

  it('renders legal status label', () => {
    render(<MemoryRouter><CasePartySection parties={mockParties as never} caseId={1} editable /></MemoryRouter>)
    // plaintiff label rendered
    expect(screen.getByText('张三')).toBeInTheDocument()
  })

  it('shows add button when editable with caseId', () => {
    render(<MemoryRouter><CasePartySection parties={[]} caseId={1} editable /></MemoryRouter>)
    expect(screen.getByText('+ 添加')).toBeInTheDocument()
  })

  it('does not show add button when not editable', () => {
    render(<MemoryRouter><CasePartySection parties={[]} caseId={1} /></MemoryRouter>)
    expect(screen.queryByText('+ 添加')).not.toBeInTheDocument()
  })

  it('does not show empty text when editable', () => {
    render(<MemoryRouter><CasePartySection parties={[]} caseId={1} editable /></MemoryRouter>)
    expect(screen.queryByText('暂无当事人')).not.toBeInTheDocument()
  })
})
