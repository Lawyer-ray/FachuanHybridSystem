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

vi.mock('../hooks/use-quote', () => ({
  useQuote: vi.fn(() => ({ data: null, isLoading: false })),
  shouldPoll: vi.fn(() => false),
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
})
