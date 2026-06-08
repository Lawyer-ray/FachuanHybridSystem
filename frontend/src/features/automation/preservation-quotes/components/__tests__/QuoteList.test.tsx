/**
 * QuoteList Component Tests
 * 测试财产保全询价列表组件
 */

vi.mock('react-router', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/lib/date', () => ({
  formatDate: () => '2026-06-15',
}))

vi.mock('../../hooks/use-quotes', () => ({
  useQuotes: vi.fn(),
}))

vi.mock('./QuoteStatusBadge', () => ({
  QuoteStatusBadge: ({ status }: { status: string }) => <span data-testid="status-badge">{status}</span>,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size, className }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} className={className as string}>{children}</button>
  ),
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children, value, onValueChange }: Record<string, unknown>) => (
    <div data-testid="select" data-value={value}>{children}</div>
  ),
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value }: { children: React.ReactNode; value: string }) => <div data-value={value}>{children}</div>,
  SelectTrigger: ({ children, className }: { children: React.ReactNode; className?: string }) => <div className={className}>{children}</div>,
  SelectValue: ({ placeholder }: { placeholder: string }) => <span>{placeholder}</span>,
}))

vi.mock('@/components/ui/table', () => ({
  Table: ({ children, className }: { children: React.ReactNode; className?: string }) => <table className={className}>{children}</table>,
  TableBody: ({ children }: { children: React.ReactNode }) => <tbody>{children}</tbody>,
  TableCell: ({ children, className, colSpan }: { children: React.ReactNode; className?: string; colSpan?: number }) => <td className={className} colSpan={colSpan}>{children}</td>,
  TableHead: ({ children, className }: { children: React.ReactNode; className?: string }) => <th className={className}>{children}</th>,
  TableHeader: ({ children }: { children: React.ReactNode }) => <thead>{children}</thead>,
  TableRow: ({ children, onClick, className }: { children: React.ReactNode; onClick?: () => void; className?: string }) => <tr onClick={onClick} className={className}>{children}</tr>,
}))

vi.mock('@/components/ui/skeleton', () => ({
  Skeleton: ({ className }: { className: string }) => <div className={className} data-testid="skeleton" />,
}))

import { render, screen } from '@testing-library/react'
import { QuoteList } from '../QuoteList'
import { useQuotes } from '../../hooks/use-quotes'

const mockQuotes = [
  {
    id: 1,
    preserve_amount: '500000',
    status: 'success',
    success_count: 3,
    failed_count: 0,
    created_at: '2026-06-15T10:00:00Z',
  },
  {
    id: 2,
    preserve_amount: '1000000',
    status: 'pending',
    success_count: 0,
    failed_count: 0,
    created_at: '2026-06-15T11:00:00Z',
  },
]

describe('QuoteList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders create button when onCreateClick provided', () => {
    vi.mocked(useQuotes).mockReturnValue({ data: { items: [], total: 0 }, isLoading: false, isFetching: false } as any)
    render(<QuoteList onCreateClick={vi.fn()} />)
    const createButtons = screen.getAllByText('创建询价'); expect(createButtons.length).toBeGreaterThan(0)
  })

  it('renders status filter', () => {
    vi.mocked(useQuotes).mockReturnValue({ data: { items: [], total: 0 }, isLoading: false, isFetching: false } as any)
    render(<QuoteList />)
    expect(screen.getByText('全部状态')).toBeInTheDocument()
  })

  it('renders loading skeleton when loading', () => {
    vi.mocked(useQuotes).mockReturnValue({ data: undefined, isLoading: true, isFetching: true } as any)
    render(<QuoteList />)
    const skeletons = screen.getAllByTestId('skeleton')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('renders empty state when no quotes', () => {
    vi.mocked(useQuotes).mockReturnValue({ data: { items: [], total: 0 }, isLoading: false, isFetching: false } as any)
    render(<QuoteList />)
    expect(screen.getByText('暂无询价任务')).toBeInTheDocument()
  })

  it('renders quote rows when data is available', () => {
    vi.mocked(useQuotes).mockReturnValue({ data: { items: mockQuotes, total: 2 }, isLoading: false, isFetching: false } as any)
    render(<QuoteList />)
    expect(screen.getByText(/500,000/)).toBeInTheDocument()
    expect(screen.getByText(/1,000,000/)).toBeInTheDocument()
  })

  it('renders success and failed counts', () => {
    vi.mocked(useQuotes).mockReturnValue({ data: { items: mockQuotes, total: 2 }, isLoading: false, isFetching: false } as any)
    render(<QuoteList />)
    const successEls = screen.getAllByText('3'); expect(successEls.length).toBeGreaterThan(0)
    const zeroEls = screen.getAllByText('0'); expect(zeroEls.length).toBeGreaterThan(0)
  })

  it('renders table headers', () => {
    vi.mocked(useQuotes).mockReturnValue({ data: { items: [], total: 0 }, isLoading: false, isFetching: false } as any)
    render(<QuoteList />)
    expect(screen.getByText('保全金额')).toBeInTheDocument()
    expect(screen.getByText('状态')).toBeInTheDocument()
    expect(screen.getByText('成功/失败')).toBeInTheDocument()
    expect(screen.getByText('创建时间')).toBeInTheDocument()
  })
})
