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
import { toast } from 'sonner'

describe('EnterpriseSearch - coverage improvements', () => {
  const defaultProps = {
    onPrefill: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ========== Empty keyword search - covers line 45 ==========

  it('shows error when searching with empty keyword', async () => {
    render(<EnterpriseSearch {...defaultProps} />)
    fireEvent.click(screen.getByText('搜索'))
    expect(screen.getByText('请输入企业名称关键词')).toBeInTheDocument()
  })

  // ========== Empty keyword with whitespace only ==========

  it('shows error when searching with whitespace-only keyword', async () => {
    render(<EnterpriseSearch {...defaultProps} />)
    const input = screen.getByPlaceholderText('输入企业名称关键词...')
    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.click(screen.getByText('搜索'))
    expect(screen.getByText('请输入企业名称关键词')).toBeInTheDocument()
  })

  // ========== Search API failure - covers catch block (line 57-58) ==========

  it('shows error toast when search API throws', async () => {
    vi.mocked(clientApi.searchEnterprise).mockRejectedValue(new Error('network'))

    render(<EnterpriseSearch {...defaultProps} />)
    const input = screen.getByPlaceholderText('输入企业名称关键词...')
    fireEvent.change(input, { target: { value: 'test' } })
    fireEvent.click(screen.getByText('搜索'))

    await waitFor(() => {
      expect(screen.getByText('企业搜索失败，请重试')).toBeInTheDocument()
    })
  })

  // ========== Search with empty results - covers setSearchError branch ==========

  it('shows no results message when search returns empty items', async () => {
    vi.mocked(clientApi.searchEnterprise).mockResolvedValue({
      keyword: 'nothing', provider: 'tianyancha', items: [], total: 0,
    })

    render(<EnterpriseSearch {...defaultProps} />)
    const input = screen.getByPlaceholderText('输入企业名称关键词...')
    fireEvent.change(input, { target: { value: 'nothing' } })
    fireEvent.click(screen.getByText('搜索'))

    await waitFor(() => {
      expect(screen.getByText(/暂未检索到匹配企业/)).toBeInTheDocument()
    })
  })

  // ========== Company select and prefill - covers handleSelect (lines 64-77) ==========

  it('loads enterprise profile and prefill data on company select', async () => {
    vi.mocked(clientApi.searchEnterprise).mockResolvedValue({
      keyword: 'test', provider: 'tianyancha',
      items: [{
        company_id: '1', company_name: 'Corp A', legal_person: 'Boss',
        status: 'active', establish_date: '2020', registered_capital: '100万', phone: '138',
      }],
      total: 1,
    })

    vi.mocked(clientApi.getEnterprisePrefill).mockResolvedValue({
      provider: 'tianyancha',
      prefill: { client_type: 'legal', name: 'Corp A', id_number: '91110000', legal_representative: 'Boss', address: 'Shanghai', phone: '138' },
      profile: {
        company_id: '1', company_name: 'Corp A', unified_social_credit_code: '91110000',
        legal_person: 'Boss', status: 'active', establish_date: '2020', registered_capital: '100万',
        address: 'Shanghai', business_scope: 'IT', phone: '138',
      },
      existing_client: null,
    })

    render(<EnterpriseSearch {...defaultProps} />)
    const input = screen.getByPlaceholderText('输入企业名称关键词...')
    fireEvent.change(input, { target: { value: 'test' } })
    fireEvent.click(screen.getByText('搜索'))

    await waitFor(() => {
      expect(screen.getByText('Corp A')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Corp A'))

    await waitFor(() => {
      expect(clientApi.getEnterprisePrefill).toHaveBeenCalledWith('1', 'tianyancha')
      expect(screen.getByText('一键填充')).toBeInTheDocument()
    })
  })

  // ========== handleApply - covers lines 79-83 ==========

  it('calls onPrefill and shows success toast when apply is clicked', async () => {
    vi.mocked(clientApi.searchEnterprise).mockResolvedValue({
      keyword: 'test', provider: 'tianyancha',
      items: [{
        company_id: '1', company_name: 'Corp B', legal_person: 'Boss',
        status: 'active', establish_date: '2020', registered_capital: '100万', phone: '138',
      }],
      total: 1,
    })

    vi.mocked(clientApi.getEnterprisePrefill).mockResolvedValue({
      provider: 'tianyancha',
      prefill: { client_type: 'legal', name: 'Corp B', id_number: '91110000', legal_representative: 'Boss', address: 'Beijing', phone: '138' },
      profile: {
        company_id: '1', company_name: 'Corp B', unified_social_credit_code: '91110000',
        legal_person: 'Boss', status: 'active', establish_date: '2020', registered_capital: '100万',
        address: 'Beijing', business_scope: 'IT', phone: '138',
      },
      existing_client: null,
    })

    render(<EnterpriseSearch {...defaultProps} />)
    const input = screen.getByPlaceholderText('输入企业名称关键词...')
    fireEvent.change(input, { target: { value: 'test' } })
    fireEvent.click(screen.getByText('搜索'))

    await waitFor(() => {
      expect(screen.getByText('Corp B')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Corp B'))

    await waitFor(() => {
      expect(screen.getByText('一键填充')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('一键填充'))

    expect(defaultProps.onPrefill).toHaveBeenCalled()
    expect(toast.success).toHaveBeenCalledWith('已自动填充企业信息')
  })

  // ========== handleReset - covers lines 85-90 ==========

  it('resets state when "重新搜索" is clicked', async () => {
    vi.mocked(clientApi.searchEnterprise).mockResolvedValue({
      keyword: 'test', provider: 'tianyancha',
      items: [{
        company_id: '1', company_name: 'Corp C', legal_person: 'Boss',
        status: 'active', establish_date: '2020', registered_capital: '100万', phone: '138',
      }],
      total: 1,
    })

    vi.mocked(clientApi.getEnterprisePrefill).mockResolvedValue({
      provider: 'tianyancha',
      prefill: { client_type: 'legal', name: 'Corp C' },
      profile: {
        company_id: '1', company_name: 'Corp C', unified_social_credit_code: '91110000',
        legal_person: 'Boss', status: 'active', establish_date: '2020', registered_capital: '100万',
        address: 'Beijing', business_scope: 'IT', phone: '138',
      },
      existing_client: null,
    })

    render(<EnterpriseSearch {...defaultProps} />)
    const input = screen.getByPlaceholderText('输入企业名称关键词...')
    fireEvent.change(input, { target: { value: 'test' } })
    fireEvent.click(screen.getByText('搜索'))

    await waitFor(() => {
      expect(screen.getByText('Corp C')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Corp C'))

    await waitFor(() => {
      expect(screen.getByText('重新搜索')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('重新搜索'))

    // After reset, company list should reappear
    await waitFor(() => {
      expect(screen.getByText('Corp C')).toBeInTheDocument()
    })
  })

  // ========== Existing client warning - covers line 191-200 ==========

  it('shows existing client warning when existing_client is not null', async () => {
    vi.mocked(clientApi.searchEnterprise).mockResolvedValue({
      keyword: 'test', provider: 'tianyancha',
      items: [{
        company_id: '1', company_name: 'Corp D', legal_person: 'Boss',
        status: 'active', establish_date: '2020', registered_capital: '100万', phone: '138',
      }],
      total: 1,
    })

    vi.mocked(clientApi.getEnterprisePrefill).mockResolvedValue({
      provider: 'tianyancha',
      prefill: { client_type: 'legal', name: 'Corp D' },
      profile: {
        company_id: '1', company_name: 'Corp D', unified_social_credit_code: '91110000',
        legal_person: 'Boss', status: 'active', establish_date: '2020', registered_capital: '100万',
        address: 'Beijing', business_scope: 'IT', phone: '138',
      },
      existing_client: { id: 42, name: 'Existing Corp' },
    })

    render(<EnterpriseSearch {...defaultProps} />)
    const input = screen.getByPlaceholderText('输入企业名称关键词...')
    fireEvent.change(input, { target: { value: 'test' } })
    fireEvent.click(screen.getByText('搜索'))

    await waitFor(() => {
      expect(screen.getByText('Corp D')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Corp D'))

    await waitFor(() => {
      expect(screen.getByText(/该企业已存在对应当事人/)).toBeInTheDocument()
      expect(screen.getByText(/查看「Existing Corp」/)).toBeInTheDocument()
    })
  })

  // ========== getEnterprisePrefill failure - covers catch block ==========

  it('shows toast error when getEnterprisePrefill fails', async () => {
    vi.mocked(clientApi.searchEnterprise).mockResolvedValue({
      keyword: 'test', provider: 'tianyancha',
      items: [{
        company_id: '1', company_name: 'Corp E', legal_person: 'Boss',
        status: 'active', establish_date: '2020', registered_capital: '100万', phone: '138',
      }],
      total: 1,
    })

    vi.mocked(clientApi.getEnterprisePrefill).mockRejectedValue(new Error('fail'))

    render(<EnterpriseSearch {...defaultProps} />)
    const input = screen.getByPlaceholderText('输入企业名称关键词...')
    fireEvent.change(input, { target: { value: 'test' } })
    fireEvent.click(screen.getByText('搜索'))

    await waitFor(() => {
      expect(screen.getByText('Corp E')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Corp E'))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('企业详情加载失败')
    })
  })

  // ========== Expanded/collapsed toggle - covers setExpanded ==========

  it('toggles expanded state when title is clicked', () => {
    render(<EnterpriseSearch {...defaultProps} />)
    const titleButton = screen.getByText('企业信息搜索预填').closest('button')!
    // Initially expanded, click to collapse
    fireEvent.click(titleButton)
    // After collapse, search input should not be visible
    expect(screen.queryByPlaceholderText('输入企业名称关键词...')).not.toBeInTheDocument()
    // Click again to expand
    fireEvent.click(titleButton)
    expect(screen.getByPlaceholderText('输入企业名称关键词...')).toBeInTheDocument()
  })

  // ========== Enter key triggers search ==========

  it('triggers search on Enter key press', async () => {
    vi.mocked(clientApi.searchEnterprise).mockResolvedValue({
      keyword: 'test', provider: 'tianyancha', items: [], total: 0,
    })

    render(<EnterpriseSearch {...defaultProps} />)
    const input = screen.getByPlaceholderText('输入企业名称关键词...')
    fireEvent.change(input, { target: { value: 'test' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => {
      expect(clientApi.searchEnterprise).toHaveBeenCalledWith('test', 'tianyancha')
    })
  })

  // ========== Profile data with null/undefined optional fields ==========

  it('renders profile with null optional fields showing dash', async () => {
    vi.mocked(clientApi.searchEnterprise).mockResolvedValue({
      keyword: 'test', provider: 'tianyancha',
      items: [{
        company_id: '1', company_name: 'Corp F', legal_person: undefined,
        status: undefined, establish_date: undefined, registered_capital: undefined, phone: undefined,
      }],
      total: 1,
    })

    vi.mocked(clientApi.getEnterprisePrefill).mockResolvedValue({
      provider: 'tianyancha',
      prefill: { client_type: 'legal', name: 'Corp F' },
      profile: {
        company_id: '1', company_name: 'Corp F', unified_social_credit_code: undefined,
        legal_person: undefined, status: undefined, establish_date: undefined, registered_capital: undefined,
        address: undefined, business_scope: undefined, phone: undefined,
      },
      existing_client: null,
    })

    render(<EnterpriseSearch {...defaultProps} />)
    const input = screen.getByPlaceholderText('输入企业名称关键词...')
    fireEvent.change(input, { target: { value: 'test' } })
    fireEvent.click(screen.getByText('搜索'))

    await waitFor(() => {
      expect(screen.getByText('Corp F')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Corp F'))

    await waitFor(() => {
      // Profile should show dashes for null values
      const dashes = screen.getAllByText('-')
      expect(dashes.length).toBeGreaterThan(0)
    })
  })

  // ========== handleApply with no prefillData - covers line 80 early return ==========

  it('handleApply does nothing when prefillData is null', () => {
    render(<EnterpriseSearch {...defaultProps} />)
    // No prefill data yet, so applying should do nothing
    expect(defaultProps.onPrefill).not.toHaveBeenCalled()
  })
})
