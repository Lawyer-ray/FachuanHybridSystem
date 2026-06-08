vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  SelectContent: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  SelectItem: ({ children, value }: Record<string, unknown>) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  SelectValue: () => <span />,
}))

vi.mock('lucide-react', () => {
  const Icon = (p: Record<string, unknown>) => <svg data-testid="icon" {...p} />
  return {
    Search: Icon, Building2: Icon, Loader2: Icon, AlertTriangle: Icon,
    ExternalLink: Icon, Sparkles: Icon, ChevronDown: Icon,
  }
})

vi.mock('framer-motion', () => ({
  motion: {
    div: (p: Record<string, unknown>) => <div {...p}>{(p as Record<string, unknown>).children}</div>,
  },
  AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

vi.mock('../../api', () => ({
  clientApi: {
    searchEnterprise: vi.fn(),
    getEnterprisePrefill: vi.fn(),
  },
}))

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { EnterpriseSearch } from '../EnterpriseSearch'
import { clientApi } from '../../api'

describe('EnterpriseSearch', () => {
  const defaultProps = {
    onPrefill: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the title', () => {
    render(<EnterpriseSearch {...defaultProps} />)
    expect(screen.getByText('企业信息搜索预填')).toBeInTheDocument()
  })

  it('renders search input', () => {
    render(<EnterpriseSearch {...defaultProps} />)
    expect(screen.getByPlaceholderText('输入企业名称关键词...')).toBeInTheDocument()
  })

  it('renders search button', () => {
    render(<EnterpriseSearch {...defaultProps} />)
    expect(screen.getByText('搜索')).toBeInTheDocument()
  })

  it('shows hint text', () => {
    render(<EnterpriseSearch {...defaultProps} />)
    expect(screen.getByText('法人 / 非法人组织')).toBeInTheDocument()
  })

  it('calls searchEnterprise API on search', async () => {
    vi.mocked(clientApi.searchEnterprise).mockResolvedValue({
      keyword: 'test',
      provider: 'tianyancha',
      items: [],
      total: 0,
    })

    render(<EnterpriseSearch {...defaultProps} />)
    const input = screen.getByPlaceholderText('输入企业名称关键词...')
    fireEvent.change(input, { target: { value: 'test' } })
    fireEvent.click(screen.getByText('搜索'))

    await waitFor(() => {
      expect(clientApi.searchEnterprise).toHaveBeenCalledWith('test', 'tianyancha')
    })
  })

  it('displays search results when found', async () => {
    vi.mocked(clientApi.searchEnterprise).mockResolvedValue({
      keyword: 'test',
      provider: 'tianyancha',
      items: [
        {
          company_id: '1',
          company_name: 'Test Corp',
          legal_person: 'Wang',
          status: 'active',
          establish_date: '2020-01-01',
          registered_capital: '100万',
          phone: '00000000000',
        },
      ],
      total: 1,
    })

    render(<EnterpriseSearch {...defaultProps} />)
    const input = screen.getByPlaceholderText('输入企业名称关键词...')
    fireEvent.change(input, { target: { value: 'test' } })
    fireEvent.click(screen.getByText('搜索'))

    await waitFor(() => {
      expect(screen.getByText('Test Corp')).toBeInTheDocument()
    })
  })

  it('displays empty state when no results', async () => {
    vi.mocked(clientApi.searchEnterprise).mockResolvedValue({
      keyword: 'test',
      provider: 'tianyancha',
      items: [],
      total: 0,
    })

    render(<EnterpriseSearch {...defaultProps} />)
    const input = screen.getByPlaceholderText('输入企业名称关键词...')
    fireEvent.change(input, { target: { value: 'test' } })
    fireEvent.click(screen.getByText('搜索'))

    await waitFor(() => {
      expect(screen.getByText(/暂未检索到匹配企业/)).toBeInTheDocument()
    })
  })

  it('calls getEnterprisePrefill when a company is selected', async () => {
    const prefillData = {
      provider: 'tianyancha',
      prefill: { client_type: 'legal', name: 'Test Corp', id_number: '91110000', legal_representative: 'Wang', address: 'Beijing', phone: '138' },
      profile: {
        company_id: '1', company_name: 'Test Corp', unified_social_credit_code: '91110000',
        legal_person: 'Wang', status: 'active', establish_date: '2020', registered_capital: '100万',
        address: 'Beijing', business_scope: 'IT', phone: '138',
      },
      existing_client: null,
    }

    vi.mocked(clientApi.searchEnterprise).mockResolvedValue({
      keyword: 'test', provider: 'tianyancha',
      items: [{
        company_id: '1', company_name: 'Test Corp', legal_person: 'Wang',
        status: 'active', establish_date: '2020', registered_capital: '100万', phone: '138',
      }],
      total: 1,
    })

    vi.mocked(clientApi.getEnterprisePrefill).mockResolvedValue(prefillData)

    render(<EnterpriseSearch {...defaultProps} />)
    const input = screen.getByPlaceholderText('输入企业名称关键词...')
    fireEvent.change(input, { target: { value: 'test' } })
    fireEvent.click(screen.getByText('搜索'))

    await waitFor(() => {
      expect(screen.getByText('Test Corp')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Test Corp'))

    await waitFor(() => {
      expect(clientApi.getEnterprisePrefill).toHaveBeenCalledWith('1', 'tianyancha')
    })
  })
})
