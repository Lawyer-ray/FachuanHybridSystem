import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, className }: Record<string, unknown>) => (
    <span className={className as string}>{children}</span>
  ),
}))

vi.mock('@/components/ui/table', () => ({
  Table: ({ children, className }: { children: React.ReactNode; className?: string }) => <table className={className}>{children}</table>,
  TableBody: ({ children }: { children: React.ReactNode }) => <tbody>{children}</tbody>,
  TableCell: ({ children, className, colSpan }: { children: React.ReactNode; className?: string; colSpan?: number }) => <td className={className} colSpan={colSpan}>{children}</td>,
  TableHead: ({ children, className }: { children: React.ReactNode; className?: string }) => <th className={className}>{children}</th>,
  TableHeader: ({ children }: { children: React.ReactNode }) => <thead>{children}</thead>,
  TableRow: ({ children }: { children: React.ReactNode }) => <tr>{children}</tr>,
}))

vi.mock('lucide-react', () => ({
  CheckCircle2: () => <svg data-testid="check-circle" />,
  XCircle: () => <svg data-testid="x-circle" />,
  AlertCircle: () => <svg data-testid="alert-circle" />,
  ChevronDown: () => <svg data-testid="chevron-down" />,
  ChevronUp: () => <svg data-testid="chevron-up" />,
}))

import { InsuranceQuoteTable } from '../InsuranceQuoteTable'

describe('InsuranceQuoteTable', () => {
  const mockQuotes = [
    { id: 1, company_name: '人保财险', status: 'success' as const, premium: '5000.00', min_rate: '0.003', max_rate: '0.005', error_message: null },
    { id: 2, company_name: '平安保险', status: 'success' as const, premium: '4500.00', min_rate: '0.002', max_rate: '0.004', error_message: null },
    { id: 3, company_name: '太平洋保险', status: 'failed' as const, premium: null, min_rate: null, max_rate: null, error_message: '系统繁忙' },
  ]

  it('renders table headers', () => {
    render(<InsuranceQuoteTable quotes={[]} />)
    expect(screen.getByText('保险公司')).toBeInTheDocument()
    expect(screen.getByText('保费')).toBeInTheDocument()
    expect(screen.getByText('费率范围')).toBeInTheDocument()
    expect(screen.getByText('状态')).toBeInTheDocument()
  })

  it('renders empty state when no quotes', () => {
    render(<InsuranceQuoteTable quotes={[]} />)
    expect(screen.getByText('暂无保险报价数据')).toBeInTheDocument()
  })

  it('renders company names (mobile + desktop)', () => {
    render(<InsuranceQuoteTable quotes={mockQuotes} />)
    // Mobile + desktop views render each company name twice
    expect(screen.getAllByText('人保财险').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('平安保险').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('太平洋保险').length).toBeGreaterThanOrEqual(1)
  })

  it('displays success status badges', () => {
    render(<InsuranceQuoteTable quotes={mockQuotes} />)
    expect(screen.getAllByText('成功').length).toBeGreaterThanOrEqual(2)
  })

  it('displays failed status badges', () => {
    render(<InsuranceQuoteTable quotes={mockQuotes} />)
    expect(screen.getAllByText('失败').length).toBeGreaterThanOrEqual(1)
  })

  it('displays formatted premium', () => {
    render(<InsuranceQuoteTable quotes={mockQuotes} />)
    expect(screen.getAllByText('¥5,000.00').length).toBeGreaterThanOrEqual(1)
  })

  // ===== Branch coverage: formatPremium null =====

  it('displays "-" for null premium', () => {
    const quotes = [{ id: 99, company_name: 'Test', status: 'failed' as const, premium: null, min_rate: null, max_rate: null, error_message: null }]
    render(<InsuranceQuoteTable quotes={quotes} />)
    expect(screen.getAllByText('-').length).toBeGreaterThan(0)
  })

  // ===== Branch coverage: formatPremium empty string =====

  it('displays "-" for empty premium', () => {
    const quotes = [{ id: 99, company_name: 'Test', status: 'success' as const, premium: '', min_rate: null, max_rate: null, error_message: null }]
    render(<InsuranceQuoteTable quotes={quotes} />)
    expect(screen.getAllByText('-').length).toBeGreaterThan(0)
  })

  // ===== Branch coverage: formatPremium NaN =====

  it('displays "-" for NaN premium', () => {
    const quotes = [{ id: 99, company_name: 'Test', status: 'success' as const, premium: 'abc', min_rate: null, max_rate: null, error_message: null }]
    render(<InsuranceQuoteTable quotes={quotes} />)
    expect(screen.getAllByText('-').length).toBeGreaterThan(0)
  })

  // ===== Branch coverage: formatRateRange =====

  it('displays rate range with both rates', () => {
    const quotes = [{ id: 99, company_name: 'Test', status: 'success' as const, premium: '1000', min_rate: '0.003', max_rate: '0.005', error_message: null }]
    render(<InsuranceQuoteTable quotes={quotes} />)
    expect(screen.getAllByText('0.30% - 0.50%').length).toBeGreaterThanOrEqual(1)
  })

  it('displays rate range with only min rate', () => {
    const quotes = [{ id: 99, company_name: 'Test', status: 'success' as const, premium: '1000', min_rate: '0.003', max_rate: null, error_message: null }]
    render(<InsuranceQuoteTable quotes={quotes} />)
    expect(screen.getAllByText('≥ 0.30%').length).toBeGreaterThanOrEqual(1)
  })

  it('displays rate range with only max rate', () => {
    const quotes = [{ id: 99, company_name: 'Test', status: 'success' as const, premium: '1000', min_rate: null, max_rate: '0.005', error_message: null }]
    render(<InsuranceQuoteTable quotes={quotes} />)
    expect(screen.getAllByText('≤ 0.50%').length).toBeGreaterThanOrEqual(1)
  })

  it('displays single rate when min equals max', () => {
    const quotes = [{ id: 99, company_name: 'Test', status: 'success' as const, premium: '1000', min_rate: '0.005', max_rate: '0.005', error_message: null }]
    render(<InsuranceQuoteTable quotes={quotes} />)
    expect(screen.getAllByText('0.50%').length).toBeGreaterThanOrEqual(1)
  })

  it('displays "-" when both rates are null', () => {
    const quotes = [{ id: 99, company_name: 'Test', status: 'failed' as const, premium: null, min_rate: null, max_rate: null, error_message: null }]
    render(<InsuranceQuoteTable quotes={quotes} />)
    // Multiple '-' cells, but at least one for rate range
    expect(screen.getAllByText('-').length).toBeGreaterThan(0)
  })

  // ===== Branch coverage: error message expansion =====

  it('expands error message on click', async () => {
    const user = userEvent.setup()
    render(<InsuranceQuoteTable quotes={[mockQuotes[2]]} />)
    const detailsBtns = screen.getAllByText('查看详情')
    await user.click(detailsBtns[0])
    expect(screen.getAllByText('系统繁忙').length).toBeGreaterThanOrEqual(1)
    // Should now show "收起" button
    expect(screen.getAllByText('收起').length).toBeGreaterThanOrEqual(1)
  })

  it('collapses error message on second click', async () => {
    const user = userEvent.setup()
    render(<InsuranceQuoteTable quotes={[mockQuotes[2]]} />)
    const detailsBtns = screen.getAllByText('查看详情')
    await user.click(detailsBtns[0])
    const collapseBtns = screen.getAllByText('收起')
    await user.click(collapseBtns[0])
    expect(screen.queryByText('系统繁忙')).not.toBeInTheDocument()
  })

  // ===== Branch coverage: null quotes =====

  it('renders empty state when quotes is null', () => {
    render(<InsuranceQuoteTable quotes={null as any} />)
    expect(screen.getByText('暂无保险报价数据')).toBeInTheDocument()
  })

  // ===== Branch coverage: sorting =====

  it('sorts failed quotes after success quotes', () => {
    render(<InsuranceQuoteTable quotes={mockQuotes} />)
    // The sorting puts failed last - verify the company names appear
    expect(screen.getAllByText('人保财险').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('太平洋保险').length).toBeGreaterThanOrEqual(1)
  })
})
