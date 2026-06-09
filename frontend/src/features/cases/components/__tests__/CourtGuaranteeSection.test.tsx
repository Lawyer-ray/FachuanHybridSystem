import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { CourtGuaranteeSection } from '../CourtGuaranteeSection'

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})
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
})
