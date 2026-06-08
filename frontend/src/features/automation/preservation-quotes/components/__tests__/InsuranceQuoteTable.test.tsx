import { render, screen } from '@testing-library/react'
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
})
