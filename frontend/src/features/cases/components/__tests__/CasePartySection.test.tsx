import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { CasePartySection } from '../CasePartySection'
import type { CaseParty } from '../../types'

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

vi.mock('../../hooks/use-party-mutations', () => ({
  usePartyMutations: () => ({
    createParty: { mutate: mockCreateMutate, isPending: false },
    deleteParty: { mutate: mockDeleteMutate, isPending: false },
  }),
}))

vi.mock('@/features/contracts/hooks/use-clients-select', () => ({
  useClientsSelect: vi.fn().mockReturnValue({ data: [] }),
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
vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}))

vi.mock('lucide-react', () => ({
  X: (p: Record<string, unknown>) => <svg data-testid="x-icon" {...p} />,
  Loader2: (p: Record<string, unknown>) => <svg data-testid="loader" {...p} />,
  Search: (p: Record<string, unknown>) => <svg data-testid="search" {...p} />,
}))

const makeParty = (overrides: Partial<CaseParty> = {}): CaseParty =>
  ({
    id: 1,
    client: 10,
    client_detail: { name: '张三', is_our_client: true, client_type: 'natural' },
    legal_status: 'plaintiff',
    ...overrides,
  }) as unknown as CaseParty

describe('CasePartySection', () => {
  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  // -- Non-editable rendering --

  it('renders empty message when no parties and not editable', () => {
    render(<CasePartySection parties={[]} />)
    expect(screen.getByText('暂无当事人')).toBeInTheDocument()
  })

  it('renders no empty message when editable without caseId (editable hides empty text)', () => {
    render(<CasePartySection parties={[]} editable />)
    expect(screen.queryByText('暂无当事人')).not.toBeInTheDocument()
  })

  it('renders party name', () => {
    render(<CasePartySection parties={[makeParty()]} />)
    expect(screen.getByText('张三')).toBeInTheDocument()
  })

  it('renders legal status label', () => {
    render(<CasePartySection parties={[makeParty()]} />)
    expect(screen.getByText(/原告/)).toBeInTheDocument()
  })

  it('renders party with null legal_status (no status label)', () => {
    render(<CasePartySection parties={[makeParty({ legal_status: null })]} />)
    expect(screen.getByText('张三')).toBeInTheDocument()
    expect(screen.queryByText(/原告/)).not.toBeInTheDocument()
  })

  it('renders party with unknown legal_status fallback', () => {
    render(<CasePartySection parties={[makeParty({ legal_status: 'unknown_status' as any })]} />)
    expect(screen.getByText(/unknown_status/)).toBeInTheDocument()
  })

  it('renders party name fallback when client_detail.name is null', () => {
    render(
      <CasePartySection
        parties={[makeParty({ client_detail: { name: null, is_our_client: true, client_type: 'natural' } as any })]}
      />,
    )
    expect(screen.getByText('未知')).toBeInTheDocument()
  })

  // -- Editable mode --

  it('shows delete button in editable mode with caseId', () => {
    render(<CasePartySection parties={[makeParty()]} editable caseId={1} />)
    expect(screen.getByTestId('x-icon')).toBeInTheDocument()
  })

  it('does not show delete button when not editable', () => {
    render(<CasePartySection parties={[makeParty()]} />)
    expect(screen.queryByTestId('x-icon')).not.toBeInTheDocument()
  })

  it('does not show delete button when caseId is missing', () => {
    render(<CasePartySection parties={[makeParty()]} editable />)
    expect(screen.queryByTestId('x-icon')).not.toBeInTheDocument()
  })

  it('shows add button in editable mode with caseId', () => {
    render(<CasePartySection parties={[]} editable caseId={1} />)
    expect(screen.getByText('+ 添加')).toBeInTheDocument()
  })

  it('does not show add button when not editable', () => {
    render(<CasePartySection parties={[]} />)
    expect(screen.queryByText('+ 添加')).not.toBeInTheDocument()
  })

  // -- Mutations --

  it('calls deleteParty.mutate on delete click', () => {
    render(<CasePartySection parties={[makeParty()]} editable caseId={1} />)
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
    render(<CasePartySection parties={[makeParty()]} editable caseId={1} />)
    fireEvent.click(screen.getByTestId('x-icon').closest('button')!)
    expect(toast.success).toHaveBeenCalledWith('已删除')
  })

  it('shows error toast on delete failure', () => {
    mockDeleteMutate.mockImplementation((_id: number, opts: { onError: (e: Error) => void }) => {
      opts.onError(new Error('delete failed'))
    })
    render(<CasePartySection parties={[makeParty()]} editable caseId={1} />)
    fireEvent.click(screen.getByTestId('x-icon').closest('button')!)
    expect(toast.error).toHaveBeenCalledWith('delete failed')
  })

  it('shows generic error toast when error has no message', () => {
    mockDeleteMutate.mockImplementation((_id: number, opts: { onError: (e: Error) => void }) => {
      opts.onError(new Error(''))
    })
    render(<CasePartySection parties={[makeParty()]} editable caseId={1} />)
    fireEvent.click(screen.getByTestId('x-icon').closest('button')!)
    expect(toast.error).toHaveBeenCalledWith('删除失败')
  })

  // -- Multiple parties --

  it('renders multiple parties', () => {
    const parties = [
      makeParty({ id: 1, client: 10, client_detail: { name: '张三', is_our_client: true, client_type: 'natural' }, legal_status: 'plaintiff' }),
      makeParty({ id: 2, client: 20, client_detail: { name: '李四', is_our_client: false, client_type: 'legal' }, legal_status: 'defendant' }),
    ]
    render(<CasePartySection parties={parties as any} />)
    expect(screen.getByText('张三')).toBeInTheDocument()
    expect(screen.getByText('李四')).toBeInTheDocument()
  })

  // -- Default export --

  it('has a default export', async () => {
    const mod = await import('../CasePartySection')
    expect(mod.default).toBe(mod.CasePartySection)
  })
})
