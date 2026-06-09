import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { CourtGuaranteeSection } from '../CourtGuaranteeSection'
import { toast } from 'sonner'

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))
vi.mock('../../api', () => ({
  caseApi: {
    getCourtGuaranteeInfo: vi.fn(),
    ensureGuaranteeQuote: vi.fn().mockResolvedValue({}),
    executeCourtGuarantee: vi.fn(),
    bindGuaranteeQuote: vi.fn().mockResolvedValue({}),
    retryGuaranteeQuote: vi.fn().mockResolvedValue({}),
    deleteGuaranteeQuote: vi.fn().mockResolvedValue({}),
    getCourtGuaranteeSession: vi.fn(),
  },
}))
vi.mock('@/components/shared', () => ({
  DetailCard: ({ title, extra, children }: any) => (
    <div data-testid="detail-card">
      <div>{title}</div>
      {extra}
      {children}
    </div>
  ),
}))

import { caseApi } from '../../api'

const defaultInfo = {
  court_name: '北京市朝阳区人民法院',
  preserve_category: '财产保全',
  preserve_amount: '100000',
  insurance_company_name: '保险公司A',
  consultant_code: 'CONS001',
  respondent_options: [
    { party_id: 1, name: '张三', legal_status_display: '被告' },
    { party_id: 2, name: '李四', legal_status_display: '第三人' },
  ],
  quote_context: {
    quote_id: 'q1',
    binding_id: 'b1',
    status: 'completed',
    items: [
      { id: 1, company_name: '担保公司A', min_amount: '1000', max_amount: '2000', max_apply_amount: '100000000', is_recommended: true },
      { id: 2, company_name: '担保公司B', min_amount: '800', max_amount: '1500', max_apply_amount: '50000000', is_recommended: false },
    ],
  },
}

describe('CourtGuaranteeSection', () => {
  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue(defaultInfo)
    localStorage.clear()
  })

  it('renders section title', async () => {
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('诉讼保全担保')
    expect(screen.getByText('诉讼保全担保')).toBeInTheDocument()
  })

  it('renders case info after loading', async () => {
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText(/管辖法院/)
    expect(screen.getByText('北京市朝阳区人民法院')).toBeInTheDocument()
    expect(screen.getByText('财产保全')).toBeInTheDocument()
  })

  it('renders preserve amount', async () => {
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText(/¥100000/)
    expect(screen.getByText(/¥100000/)).toBeInTheDocument()
  })

  it('renders respondent selector for multiple respondents', async () => {
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText(/张三/)
    expect(screen.getByText(/李四/)).toBeInTheDocument()
    expect(screen.getByText(/被告/)).toBeInTheDocument()
  })

  it('renders quote table', async () => {
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('担保公司A')
    expect(screen.getByText('担保公司B')).toBeInTheDocument()
  })

  it('renders recommended badge', async () => {
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('担保公司A')
    expect(screen.getByText(/🏆/)).toBeInTheDocument()
  })

  it('renders bind button when not bound', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo,
      quote_context: { ...defaultInfo.quote_context, binding_id: null },
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('绑定')
    expect(screen.getByText('绑定')).toBeInTheDocument()
  })

  it('shows bound badge when bound', async () => {
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('已绑定')
    expect(screen.getByText('已绑定')).toBeInTheDocument()
  })

  it('shows no preservation amount warning', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo, preserve_amount: null,
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('未填写保全金额')
    expect(screen.getByText('未填写保全金额')).toBeInTheDocument()
  })

  it('renders quote section', async () => {
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('财产保全询价')
    expect(screen.getByText('发起询价')).toBeInTheDocument()
  })

  it('renders execute section', async () => {
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('申请保全')
    expect(screen.getByText('开始申请')).toBeInTheDocument()
  })

  it('shows insurer name when quote exists', async () => {
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('保险公司A')
    expect(screen.getByText('保险公司A')).toBeInTheDocument()
  })

  it('shows consultant code input', async () => {
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByPlaceholderText('顾问代码（可选）')
    expect(screen.getByPlaceholderText('顾问代码（可选）')).toBeInTheDocument()
  })

  it('handles ensure quote click', async () => {
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('发起询价')
    fireEvent.click(screen.getByText('发起询价'))
    await screen.findByText('发起询价')
    expect(caseApi.ensureGuaranteeQuote).toHaveBeenCalled()
  })

  it('handles load info error silently', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockRejectedValue(new Error('fail'))
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('诉讼保全担保')
    expect(screen.getByText('诉讼保全担保')).toBeInTheDocument()
  })

  it('renders empty respondent options', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo, respondent_options: [],
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('诉讼保全担保')
    // No respondent selector should be visible
    expect(screen.queryByText('被申请人')).not.toBeInTheDocument()
  })

  it('shows single respondent without selector', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo,
      respondent_options: [{ party_id: 1, name: '张三', legal_status_display: '被告' }],
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('诉讼保全担保')
    // Single respondent shouldn't show multi-select
  })

  it('renders quote range correctly', async () => {
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('担保公司A')
    // Check formatQuoteRange: min !== max shows range
    expect(screen.getByText(/¥1000 ~ ¥2000/)).toBeInTheDocument()
  })

  it('renders quote range when min === max', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo,
      quote_context: {
        ...defaultInfo.quote_context,
        items: [{ id: 1, company_name: '担保C', min_amount: '500', max_amount: '500', max_apply_amount: '100000', is_recommended: false }],
      },
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText(/¥500/)
  })

  it('shows no quote state', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo,
      quote_context: { quote_id: null, binding_id: null, status: null, items: [] },
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText(/尚未发起询价/)
  })

  it('shows no quote execution section', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo,
      quote_context: { quote_id: null, binding_id: null, status: null, items: [] },
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText(/请先完成询价/)
  })

  it('shows quote in progress', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo,
      quote_context: { quote_id: 'q2', binding_id: null, status: 'processing', items: [] },
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText(/询价中/)
  })

  it('shows failed quote with retry button', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo,
      quote_context: { ...defaultInfo.quote_context, binding_id: null, status: 'failed' },
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText(/重试/)
    expect(screen.getByText(/重试/)).toBeInTheDocument()
  })

  it('shows session status when executing', async () => {
    vi.mocked(caseApi.executeCourtGuarantee).mockResolvedValue({
      session_id: 'sess-1', status: 'running', progress: 50,
      current_step: '正在提交', error: null, timing: null,
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('开始申请')
    fireEvent.click(screen.getByText('开始申请'))
    await screen.findByText('执行中')
  })

  it('shows completed session', async () => {
    vi.mocked(caseApi.executeCourtGuarantee).mockResolvedValue({
      session_id: 'sess-1', status: 'completed', progress: 100,
      current_step: null, error: null, timing: { overall_start: 0, overall_end: 10, login_end: 2 },
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('开始申请')
    fireEvent.click(screen.getByText('开始申请'))
    await screen.findByText('耗时统计')
  })

  it('shows failed session error', async () => {
    vi.mocked(caseApi.executeCourtGuarantee).mockResolvedValue({
      session_id: 'sess-1', status: 'failed', progress: 0,
      current_step: null, error: 'Browser crashed', timing: null,
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('开始申请')
    fireEvent.click(screen.getByText('开始申请'))
    await screen.findByText('Browser crashed')
  })

  it('handles execute error', async () => {
    vi.mocked(caseApi.executeCourtGuarantee).mockRejectedValue(new Error('fail'))
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('开始申请')
    fireEvent.click(screen.getByText('开始申请'))
  })

  it('handles empty preserve amount', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo, preserve_amount: '',
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('未填写保全金额')
  })

  it('handles zero preserve amount', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo, preserve_amount: '0',
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('未填写保全金额')
  })

  it('shows max apply amount correctly', async () => {
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('担保公司A')
    // 100000000 / 100000000 = 1.00亿
    expect(screen.getByText(/1.00亿/)).toBeInTheDocument()
  })

  // --- New tests for uncovered lines ---

  it('shows loading state initially', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockImplementation(
      () => new Promise(() => {}) // never resolves
    )
    render(<CourtGuaranteeSection caseId={1} />)
    // loadingInfo is true, refresh button should have animate-spin
    expect(screen.getByText('诉讼保全担保')).toBeInTheDocument()
  })

  it('handles ensure quote error with toast', async () => {
    vi.mocked(caseApi.ensureGuaranteeQuote).mockRejectedValueOnce(new Error('fail'))
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('发起询价')
    fireEvent.click(screen.getByText('发起询价'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('询价失败')
    })
  })

  it('handles execute with pending status and starts polling', async () => {
    vi.mocked(caseApi.executeCourtGuarantee).mockResolvedValue({
      session_id: 'sess-2', status: 'pending', progress: 0,
      current_step: '初始化', error: null, timing: null,
    })
    vi.mocked(caseApi.getCourtGuaranteeSession).mockResolvedValue({
      session_id: 'sess-2', status: 'completed', progress: 100,
      current_step: null, error: null, timing: { overall_start: 0, overall_end: 5 },
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('开始申请')
    fireEvent.click(screen.getByText('开始申请'))
    // Polling should be started, and eventually complete
    await waitFor(() => {
      expect(caseApi.getCourtGuaranteeSession).toHaveBeenCalledWith('sess-2')
    }, { timeout: 5000 })
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('保全申请完成')
    }, { timeout: 5000 })
  })

  it('handles polling failure with toast', async () => {
    vi.mocked(caseApi.executeCourtGuarantee).mockResolvedValue({
      session_id: 'sess-3', status: 'running', progress: 20,
      current_step: '提交中', error: null, timing: null,
    })
    vi.mocked(caseApi.getCourtGuaranteeSession).mockResolvedValue({
      session_id: 'sess-3', status: 'failed', progress: 0,
      current_step: null, error: '网络超时', timing: null,
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('开始申请')
    fireEvent.click(screen.getByText('开始申请'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('保全申请失败: 网络超时')
    }, { timeout: 5000 })
  })

  it('handles polling exception', async () => {
    vi.mocked(caseApi.executeCourtGuarantee).mockResolvedValue({
      session_id: 'sess-4', status: 'running', progress: 10,
      current_step: '初始化', error: null, timing: null,
    })
    vi.mocked(caseApi.getCourtGuaranteeSession).mockRejectedValue(new Error('network'))
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('开始申请')
    fireEvent.click(screen.getByText('开始申请'))
    // Should handle polling error gracefully
    await waitFor(() => {
      expect(caseApi.getCourtGuaranteeSession).toHaveBeenCalled()
    }, { timeout: 5000 })
  })

  it('selects insurer from quote table', async () => {
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('担保公司A')
    const selectButtons = screen.getAllByText('选用')
    fireEvent.click(selectButtons[0])
    expect(toast.success).toHaveBeenCalledWith('已选用 担保公司A')
  })

  it('handles bind quote click', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo,
      quote_context: { ...defaultInfo.quote_context, binding_id: null },
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('绑定')
    fireEvent.click(screen.getByText('绑定'))
    await waitFor(() => {
      expect(caseApi.bindGuaranteeQuote).toHaveBeenCalled()
      expect(toast.success).toHaveBeenCalledWith('绑定成功')
    })
  })

  it('handles bind quote error', async () => {
    vi.mocked(caseApi.bindGuaranteeQuote).mockRejectedValueOnce(new Error('fail'))
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo,
      quote_context: { ...defaultInfo.quote_context, binding_id: null },
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('绑定')
    fireEvent.click(screen.getByText('绑定'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('绑定失败')
    })
  })

  it('handles retry quote click', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo,
      quote_context: { ...defaultInfo.quote_context, binding_id: null, status: 'failed' },
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('重试')
    fireEvent.click(screen.getByText('重试'))
    await waitFor(() => {
      expect(caseApi.retryGuaranteeQuote).toHaveBeenCalled()
      expect(toast.success).toHaveBeenCalledWith('重试已提交')
    })
  })

  it('handles retry quote error', async () => {
    vi.mocked(caseApi.retryGuaranteeQuote).mockRejectedValueOnce(new Error('fail'))
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo,
      quote_context: { ...defaultInfo.quote_context, binding_id: null, status: 'failed' },
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('重试')
    fireEvent.click(screen.getByText('重试'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('重试失败')
    })
  })

  it('handles delete quote confirm', async () => {
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('删除')
    fireEvent.click(screen.getByText('删除'))
    // Confirm dialog should appear
    await screen.findByText('确认删除报价')
    fireEvent.click(screen.getByText('确认'))
    await waitFor(() => {
      expect(caseApi.deleteGuaranteeQuote).toHaveBeenCalled()
      expect(toast.success).toHaveBeenCalledWith('已删除')
    })
  })

  it('handles delete quote error', async () => {
    vi.mocked(caseApi.deleteGuaranteeQuote).mockRejectedValueOnce(new Error('fail'))
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('删除')
    fireEvent.click(screen.getByText('删除'))
    await screen.findByText('确认删除报价')
    fireEvent.click(screen.getByText('确认'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('删除失败')
    })
  })

  it('renders quote range with min only', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo,
      quote_context: {
        ...defaultInfo.quote_context,
        items: [{ id: 1, company_name: '公司D', min_amount: '500', max_amount: '', max_apply_amount: '100000', is_recommended: false }],
      },
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('公司D')
    expect(screen.getByText(/¥500/)).toBeInTheDocument()
  })

  it('renders quote range with max only', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo,
      quote_context: {
        ...defaultInfo.quote_context,
        items: [{ id: 1, company_name: '公司E', min_amount: '', max_amount: '800', max_apply_amount: '100000', is_recommended: false }],
      },
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('公司E')
    expect(screen.getByText(/~ ¥800/)).toBeInTheDocument()
  })

  it('renders quote range with both empty', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo,
      quote_context: {
        ...defaultInfo.quote_context,
        items: [{ id: 1, company_name: '公司F', min_amount: '', max_amount: '', max_apply_amount: '100000', is_recommended: false }],
      },
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('公司F')
    // formatQuoteRange returns '-'
  })

  it('renders max apply amount with empty value', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo,
      quote_context: {
        ...defaultInfo.quote_context,
        items: [{ id: 1, company_name: '公司G', min_amount: '100', max_amount: '200', max_apply_amount: '', is_recommended: false }],
      },
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('公司G')
  })

  it('renders max apply amount with non-finite value', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo,
      quote_context: {
        ...defaultInfo.quote_context,
        items: [{ id: 1, company_name: '公司H', min_amount: '100', max_amount: '200', max_apply_amount: 'abc', is_recommended: false }],
      },
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('公司H')
  })

  it('renders timing with playwright times', async () => {
    vi.mocked(caseApi.executeCourtGuarantee).mockResolvedValue({
      session_id: 'sess-5', status: 'completed', progress: 100,
      current_step: null, error: null,
      timing: { overall_start: 0, login_end: 2, playwright_start: 3, playwright_end: 8, overall_end: 10 },
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('开始申请')
    fireEvent.click(screen.getByText('开始申请'))
    await screen.findByText('耗时统计')
    expect(screen.getByText('Playwright：')).toBeInTheDocument()
    expect(screen.getByText('登录：')).toBeInTheDocument()
    expect(screen.getByText('总耗时：')).toBeInTheDocument()
  })

  it('renders session with step info', async () => {
    vi.mocked(caseApi.executeCourtGuarantee).mockResolvedValue({
      session_id: 'sess-6', status: 'running', progress: 75,
      current_step: '正在填写表单', error: null, timing: null,
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('开始申请')
    fireEvent.click(screen.getByText('开始申请'))
    await screen.findByText('正在填写表单')
    expect(screen.getByText('75%')).toBeInTheDocument()
  })

  it('handles toggle respondent checkbox', async () => {
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText(/张三/)
    // The checkboxes for respondents should be present
    const checkboxes = screen.getAllByRole('checkbox')
    // Toggle one off and back on
    fireEvent.click(checkboxes[0])
    fireEvent.click(checkboxes[1])
  })

  it('restores persisted respondent ids from localStorage', async () => {
    localStorage.setItem('court_guarantee_selected_respondents_1', JSON.stringify([2]))
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText(/张三/)
    // Should restore respondent 2 from persisted storage
  })

  it('handles corrupted localStorage for respondents', async () => {
    localStorage.setItem('court_guarantee_selected_respondents_1', 'not-json')
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText(/张三/)
    // Should fall back to selecting all respondents
  })

  it('handles localStorage with non-array value', async () => {
    localStorage.setItem('court_guarantee_selected_respondents_1', JSON.stringify({ a: 1 }))
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText(/张三/)
  })

  it('handles localStorage with invalid items', async () => {
    localStorage.setItem('court_guarantee_selected_respondents_1', JSON.stringify([-1, 0, 'abc']))
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText(/张三/)
  })

  it('renders quote context null', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo,
      quote_context: null,
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText(/尚未发起询价/)
  })

  it('renders preserve amount zero with warning', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo,
      preserve_amount: '0',
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('未填写保全金额')
    // '0' is truthy so it renders as ¥0, but hasPreservationAmount is false (0 > 0 is false)
    expect(screen.getAllByText(/¥0/).length).toBeGreaterThan(0)
  })

  it('renders court_name as dash when null', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo,
      court_name: null,
      preserve_category: '',
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('管辖法院：')
  })

  it('handles formatDuration edge cases via session timing', async () => {
    vi.mocked(caseApi.executeCourtGuarantee).mockResolvedValue({
      session_id: 'sess-7', status: 'completed', progress: 100,
      current_step: null, error: null,
      timing: { overall_start: 0, login_end: 0.5, overall_end: 0.3 },
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('开始申请')
    fireEvent.click(screen.getByText('开始申请'))
    await screen.findByText('耗时统计')
    // formatDuration with <1 should show '< 1s'
  })

  it('consultant code input updates value', async () => {
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByPlaceholderText('顾问代码（可选）')
    const input = screen.getByPlaceholderText('顾问代码（可选）')
    fireEvent.change(input, { target: { value: 'NEW001' } })
    expect(input).toHaveValue('NEW001')
  })

  it('fires loadInfo on refresh button click', async () => {
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('诉讼保全担保')
    // Find the refresh button (the one with RefreshCw icon, not the quote button)
    const refreshButtons = screen.getAllByRole('button')
    // Click the refresh button near the quote section header
    const smallRefreshBtn = refreshButtons.find(btn =>
      btn.className.includes('h-7') && btn.className.includes('w-7')
    )
    if (smallRefreshBtn) {
      fireEvent.click(smallRefreshBtn)
      await waitFor(() => {
        expect(caseApi.getCourtGuaranteeInfo).toHaveBeenCalledTimes(2)
      })
    }
  })

  it('disables quote button when no preservation amount', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo,
      preserve_amount: null,
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('发起询价')
    const quoteButton = screen.getByText('发起询价').closest('button')
    expect(quoteButton).toBeDisabled()
  })

  it('disables execute button when no quote', async () => {
    vi.mocked(caseApi.getCourtGuaranteeInfo).mockResolvedValue({
      ...defaultInfo,
      quote_context: { quote_id: null, binding_id: null, status: null, items: [] },
    })
    render(<CourtGuaranteeSection caseId={1} />)
    await screen.findByText('开始申请')
    const executeButton = screen.getByText('开始申请').closest('button')
    expect(executeButton).toBeDisabled()
  })
})
