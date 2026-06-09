import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CasePartySection } from '../components/CasePartySection'
import { toast } from 'sonner'
import type { CaseParty } from '../types'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('lucide-react', () => ({
  X: () => <svg data-testid="x-icon" />,
  Loader2: () => <svg data-testid="loader-icon" />,
  Search: () => <svg data-testid="search-icon" />,
}))

const mockCreateMutate = vi.fn()
const mockDeleteMutate = vi.fn()

vi.mock('../hooks/use-party-mutations', () => ({
  usePartyMutations: () => ({
    createParty: { mutate: mockCreateMutate, isPending: false },
    deleteParty: { mutate: mockDeleteMutate, isPending: false },
  }),
}))

vi.mock('@/features/contracts/hooks/use-clients-select', () => ({
  useClientsSelect: vi.fn(() => ({ data: [] })),
}))

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router')
  return { ...actual, Link: ({ children, to }: { children: React.ReactNode; to: string }) => <a href={to}>{children}</a> }
})

vi.mock('@/routes/paths', () => ({
  generatePath: { clientDetail: (id: number) => `/clients/${id}` },
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
  CommandInput: (props: Record<string, unknown>) => <input />,
  CommandItem: ({ children, onSelect }: { children: React.ReactNode; onSelect?: () => void }) => <div onClick={onSelect}>{children}</div>,
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
  SelectItem: ({ children, value }: { children: React.ReactNode; value: string }) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: ({ placeholder }: { placeholder?: string }) => <span>{placeholder}</span>,
}))

function makeParty(overrides: Partial<CaseParty> = {}): CaseParty {
  return {
    id: 1, case: 1, client: 1, legal_status: null,
    client_detail: { id: 1, name: '张三', is_our_client: true, phone: null, address: null, client_type: 'individual', id_number: null, legal_representative: null, legal_representative_id_number: null, client_type_label: '个人', identity_docs: [] },
    ...overrides,
  }
}

describe('CasePartySection', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders empty state when not editable', () => {
    render(<CasePartySection parties={[]} />)
    expect(screen.getByText('暂无当事人')).toBeInTheDocument()
  })

  it('does not render empty state when editable', () => {
    render(<CasePartySection parties={[]} editable caseId={1} />)
    expect(screen.queryByText('暂无当事人')).not.toBeInTheDocument()
  })

  it('renders party name', () => {
    render(<CasePartySection parties={[makeParty()]} />)
    expect(screen.getByText('张三')).toBeInTheDocument()
  })

  it('renders party with legal status', () => {
    const party = makeParty({ legal_status: 'plaintiff' })
    render(<CasePartySection parties={[party]} />)
    expect(screen.getByText(/原告/)).toBeInTheDocument()
  })

  it('renders party with unknown legal status', () => {
    const party = makeParty({ legal_status: 'unknown' })
    render(<CasePartySection parties={[party]} />)
    expect(screen.getByText(/unknown/)).toBeInTheDocument()
  })

  it('renders party without legal status', () => {
    render(<CasePartySection parties={[makeParty()]} />)
    // No parenthetical text for null status
    expect(screen.getByText('张三')).toBeInTheDocument()
  })

  it('renders add button when editable', () => {
    render(<CasePartySection parties={[]} editable caseId={1} />)
    expect(screen.getByText('+ 添加')).toBeInTheDocument()
  })

  it('does not render add button when not editable', () => {
    render(<CasePartySection parties={[]} />)
    expect(screen.queryByText('+ 添加')).not.toBeInTheDocument()
  })

  it('renders delete button when editable', () => {
    render(<CasePartySection parties={[makeParty()]} editable caseId={1} />)
    expect(screen.getByTestId('x-icon')).toBeInTheDocument()
  })

  it('does not render delete button when not editable', () => {
    render(<CasePartySection parties={[makeParty()]} />)
    expect(screen.queryByTestId('x-icon')).not.toBeInTheDocument()
  })

  it('handles delete success', () => {
    mockDeleteMutate.mockImplementation((_id: number, opts: { onSuccess: () => void }) => { opts.onSuccess() })
    render(<CasePartySection parties={[makeParty()]} editable caseId={1} />)
    fireEvent.click(screen.getByTestId('x-icon').closest('button')!)
    expect(toast.success).toHaveBeenCalledWith('已删除')
  })

  it('handles delete error', () => {
    mockDeleteMutate.mockImplementation((_id: number, opts: { onError: (e: Error) => void }) => { opts.onError(new Error('Delete failed')) })
    render(<CasePartySection parties={[makeParty()]} editable caseId={1} />)
    fireEvent.click(screen.getByTestId('x-icon').closest('button')!)
    expect(toast.error).toHaveBeenCalledWith('Delete failed')
  })

  it('renders link to client detail', () => {
    render(<CasePartySection parties={[makeParty()]} />)
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', '/clients/1')
  })

  it('renders party with unknown name fallback', () => {
    const party = makeParty({ client_detail: { ...makeParty().client_detail, name: '未知' } })
    render(<CasePartySection parties={[party]} />)
    expect(screen.getByText('未知')).toBeInTheDocument()
  })

  it('renders multiple parties', () => {
    const parties = [
      makeParty({ id: 1, client_detail: { ...makeParty().client_detail, id: 1, name: '原告' } }),
      makeParty({ id: 2, client: 2, client_detail: { ...makeParty().client_detail, id: 2, name: '被告' } }),
    ]
    render(<CasePartySection parties={parties} />)
    expect(screen.getByText('原告')).toBeInTheDocument()
    expect(screen.getByText('被告')).toBeInTheDocument()
  })

  it('renders add button popover content when editable', () => {
    render(<CasePartySection parties={[]} editable caseId={1} />)
    expect(screen.getByText('+ 添加')).toBeInTheDocument()
    // The popover content should also be rendered since we always render it
    expect(screen.getByText('未找到匹配客户')).toBeInTheDocument()
  })
})
