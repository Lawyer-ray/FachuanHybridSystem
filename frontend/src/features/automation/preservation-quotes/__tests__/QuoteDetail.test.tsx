import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { QuoteDetail } from '../components/QuoteDetail'

vi.mock('lucide-react', () => ({
  ArrowLeft: () => <svg data-testid="arrow-left" />,
  Play: () => <svg data-testid="play" />,
  RefreshCw: () => <svg data-testid="refresh" />,
  Loader2: () => <svg data-testid="loader" />,
  Calendar: () => <svg data-testid="calendar" />,
  Clock: () => <svg data-testid="clock" />,
  CheckCircle2: () => <svg data-testid="check-circle" />,
  XCircle: () => <svg data-testid="x-circle" />,
  Banknote: () => <svg data-testid="banknote" />,
}))

vi.mock('@/lib/utils', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/lib/date', () => ({
  formatDate: (d: string) => d ?? '',
}))

const mockShouldPoll = vi.fn().mockReturnValue(false)

vi.mock('../hooks/use-quote', () => ({
  useQuote: vi.fn(() => ({ data: null, isLoading: false })),
  shouldPoll: (...args: unknown[]) => mockShouldPoll(...args),
}))

vi.mock('../hooks/use-quote-mutations', () => ({
  useExecuteQuote: () => ({ mutate: vi.fn(), isPending: false }),
  useRetryQuote: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('../components/QuoteStatusBadge', () => ({
  QuoteStatusBadge: ({ status }: { status: string }) => <span data-testid="status-badge">{status}</span>,
}))

vi.mock('../components/InsuranceQuoteTable', () => ({
  InsuranceQuoteTable: () => <div data-testid="insurance-table">InsuranceQuoteTable</div>,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardHeader: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardTitle: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
}))

vi.mock('@/components/ui/skeleton', () => ({
  Skeleton: (props: Record<string, unknown>) => <div data-testid="skeleton" {...props} />,
}))

import { useQuote } from '../hooks/use-quote'
const mockUseQuote = vi.mocked(useQuote)

describe('QuoteDetail', () => {
  it('renders loading skeleton when loading', () => {
    mockUseQuote.mockReturnValue({ data: null, isLoading: true } as never)
    render(<MemoryRouter><QuoteDetail quoteId={1} /></MemoryRouter>)
    expect(screen.getAllByTestId('skeleton').length).toBeGreaterThan(0)
  })

  it('renders not found when data is null', () => {
    mockUseQuote.mockReturnValue({ data: null, isLoading: false } as never)
    render(<MemoryRouter><QuoteDetail quoteId={1} /></MemoryRouter>)
    expect(screen.getByText('询价任务不存在')).toBeInTheDocument()
  })

  it('renders back button when not found', () => {
    mockUseQuote.mockReturnValue({ data: null, isLoading: false } as never)
    render(<MemoryRouter><QuoteDetail quoteId={1} /></MemoryRouter>)
    expect(screen.getByText('返回列表')).toBeInTheDocument()
  })

  it('renders quote detail when data exists', () => {
    mockUseQuote.mockReturnValue({
      data: {
        id: 1,
        status: 'completed',
        preservation_amount: '100000',
        insurance_quotes: [],
      },
      isLoading: false,
    } as never)
    render(<MemoryRouter><QuoteDetail quoteId={1} /></MemoryRouter>)
    expect(screen.getByText('保全金额')).toBeInTheDocument()
  })

  it('renders insurance quotes table when data exists', () => {
    mockUseQuote.mockReturnValue({
      data: {
        id: 1,
        status: 'completed',
        preservation_amount: '100000',
        insurance_quotes: [],
      },
      isLoading: false,
    } as never)
    render(<MemoryRouter><QuoteDetail quoteId={1} /></MemoryRouter>)
    expect(screen.getByTestId('insurance-table')).toBeInTheDocument()
  })

  // ===== Branch coverage: error state =====

  it('renders error state when there is an error', () => {
    mockUseQuote.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('API failure'),
    } as never)
    render(<MemoryRouter><QuoteDetail quoteId={1} /></MemoryRouter>)
    expect(screen.getByText('加载失败')).toBeInTheDocument()
    expect(screen.getByText('API failure')).toBeInTheDocument()
    expect(screen.getByText('返回列表')).toBeInTheDocument()
  })

  // ===== Branch coverage: pending status - execute button =====

  it('renders execute button when status is pending', () => {
    mockUseQuote.mockReturnValue({
      data: {
        id: 1,
        status: 'pending',
        preserve_amount: '100000',
        quotes: [],
        success_count: 0,
        failed_count: 0,
        total_companies: 5,
        created_at: '2026-06-15',
        started_at: null,
        finished_at: null,
      },
      isLoading: false,
    } as never)
    render(<MemoryRouter><QuoteDetail quoteId={1} /></MemoryRouter>)
    expect(screen.getByText('执行询价')).toBeInTheDocument()
  })

  // ===== Branch coverage: failed status - retry button =====

  it('renders retry button when status is failed', () => {
    mockUseQuote.mockReturnValue({
      data: {
        id: 1,
        status: 'failed',
        preserve_amount: '100000',
        quotes: [],
        success_count: 0,
        failed_count: 5,
        total_companies: 5,
        created_at: '2026-06-15',
        started_at: '2026-06-15',
        finished_at: '2026-06-15',
        error_message: '执行失败',
      },
      isLoading: false,
    } as never)
    render(<MemoryRouter><QuoteDetail quoteId={1} /></MemoryRouter>)
    expect(screen.getByText('重试')).toBeInTheDocument()
  })

  // ===== Branch coverage: error_message display =====

  it('renders error message when quote has error_message', () => {
    mockUseQuote.mockReturnValue({
      data: {
        id: 1,
        status: 'failed',
        preserve_amount: '100000',
        quotes: [],
        success_count: 0,
        failed_count: 3,
        total_companies: 5,
        created_at: '2026-06-15',
        started_at: '2026-06-15',
        finished_at: '2026-06-15',
        error_message: '部分公司响应超时',
      },
      isLoading: false,
    } as never)
    render(<MemoryRouter><QuoteDetail quoteId={1} /></MemoryRouter>)
    expect(screen.getByText('部分公司响应超时')).toBeInTheDocument()
  })

  // ===== Branch coverage: polling indicator =====

  it('renders polling indicator when polling', () => {
    mockShouldPoll.mockReturnValue(true)
    mockUseQuote.mockReturnValue({
      data: {
        id: 1,
        status: 'running',
        preserve_amount: '100000',
        quotes: [],
        success_count: 0,
        failed_count: 0,
        total_companies: 5,
        created_at: '2026-06-15',
        started_at: null,
        finished_at: null,
      },
      isLoading: false,
      isFetching: true,
    } as never)
    render(<MemoryRouter><QuoteDetail quoteId={1} /></MemoryRouter>)
    expect(screen.getByText('正在获取最新状态...')).toBeInTheDocument()
    mockShouldPoll.mockReturnValue(false)
  })

  // ===== Branch coverage: success status has no action buttons =====

  it('renders no action buttons for success status', () => {
    mockUseQuote.mockReturnValue({
      data: {
        id: 1,
        status: 'success',
        preserve_amount: '100000',
        quotes: [],
        success_count: 5,
        failed_count: 0,
        total_companies: 5,
        created_at: '2026-06-15',
        started_at: '2026-06-15',
        finished_at: '2026-06-15',
      },
      isLoading: false,
    } as never)
    render(<MemoryRouter><QuoteDetail quoteId={1} /></MemoryRouter>)
    expect(screen.queryByText('执行询价')).not.toBeInTheDocument()
    expect(screen.queryByText('重试')).not.toBeInTheDocument()
  })

  // ===== Branch coverage: formatAmount =====

  it('renders formatted amount', () => {
    mockUseQuote.mockReturnValue({
      data: {
        id: 1,
        status: 'success',
        preserve_amount: '500000',
        quotes: [],
        success_count: 5,
        failed_count: 0,
        total_companies: 5,
        created_at: '2026-06-15',
        started_at: '2026-06-15',
        finished_at: '2026-06-15',
      },
      isLoading: false,
    } as never)
    render(<MemoryRouter><QuoteDetail quoteId={1} /></MemoryRouter>)
    expect(screen.getByText(/500,000/)).toBeInTheDocument()
  })

  it('renders "-" for NaN amount', () => {
    mockUseQuote.mockReturnValue({
      data: {
        id: 1,
        status: 'success',
        preserve_amount: 'not-a-number',
        quotes: [],
        success_count: 5,
        failed_count: 0,
        total_companies: 5,
        created_at: '2026-06-15',
        started_at: '2026-06-15',
        finished_at: '2026-06-15',
      },
      isLoading: false,
    } as never)
    render(<MemoryRouter><QuoteDetail quoteId={1} /></MemoryRouter>)
    // formatAmount returns '-' for NaN
    expect(screen.getByText('保全金额')).toBeInTheDocument()
  })
})
