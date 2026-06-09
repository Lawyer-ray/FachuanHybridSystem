import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { CourtFilingSection } from '../CourtFilingSection'
import type { Case } from '../../types'
import { caseApi } from '../../api'

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})
vi.mock('../../api', () => ({
  caseApi: {
    getCourtFilingInfo: vi.fn(),
    executeCourtFiling: vi.fn(),
    getCourtFilingSession: vi.fn(),
  },
}))
vi.mock('@/lib/format', () => ({
  formatAmount: (v: number | null) => (v != null ? `¥${v}` : '-'),
}))

const defaultFilingInfo = {
  court_name: '北京市朝阳区人民法院',
  suggested_filing_type: 'civil',
  default_filing_engine: 'playwright',
  has_http_plugin: true,
  has_court_credential: true,
  our_party_is_plaintiff_side: true,
  material_slots: [
    { slot_name: '起诉状', matched_file: 'complaint.docx', required: true },
    { slot_name: '证据目录', matched_file: null, required: false },
  ],
}

const defaultExecuteResult = {
  success: true,
  message: '立案成功',
  status: 'completed',
  session_id: null,
  timing: { overall_start: 0, overall_end: 10, login_end: 2 },
}

const baseCaseData = {
  id: 1,
  name: 'Test Case',
  cause_of_action: '合同纠纷',
  target_amount: 100000,
  supervising_authorities: [{ id: 1, name: '北京市朝阳区人民法院', authority_type: 'trial' }],
} as unknown as Case

describe('CourtFilingSection', () => {
  beforeEach(() => {
    cleanup()
    vi.mocked(caseApi.getCourtFilingInfo).mockReset()
    vi.mocked(caseApi.executeCourtFiling).mockReset()
    vi.mocked(caseApi.getCourtFilingInfo).mockResolvedValue(defaultFilingInfo)
    vi.mocked(caseApi.executeCourtFiling).mockResolvedValue(defaultExecuteResult)
  })

  it('shows loading state', () => {
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('renders filing info after loading', async () => {
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('法院一张网在线立案')
    expect(screen.getByText(/民事一审/)).toBeInTheDocument()
  })

  it('renders execute button', async () => {
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('开始一张网立案')
    expect(screen.getByText('开始一张网立案')).toBeInTheDocument()
  })

  it('renders case info summary', async () => {
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('合同纠纷')
    expect(screen.getByText('合同纠纷')).toBeInTheDocument()
  })

  it('renders material slots', async () => {
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('材料匹配')
    expect(screen.getByText('起诉状')).toBeInTheDocument()
    expect(screen.getByText('complaint.docx')).toBeInTheDocument()
  })

  it('shows unmatched required slot', async () => {
    vi.mocked(caseApi.getCourtFilingInfo).mockResolvedValue({
      ...defaultFilingInfo,
      material_slots: [
        { slot_name: '起诉状', matched_file: null, required: true },
      ],
    })
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('材料匹配')
    expect(screen.getByText('未匹配（必需）')).toBeInTheDocument()
  })

  it('renders radio buttons for filing engine', async () => {
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText(/立案引擎/)
    const radios = screen.getAllByRole('radio')
    expect(radios.length).toBeGreaterThanOrEqual(2)
  })

  it('shows no court hint', async () => {
    vi.mocked(caseApi.getCourtFilingInfo).mockResolvedValue({
      ...defaultFilingInfo, court_name: '',
    })
    render(<CourtFilingSection caseId={1} caseData={{ ...baseCaseData, supervising_authorities: [] } as any} />)
    await screen.findByText(/请先设置管辖法院/)
  })

  it('shows not plaintiff hint', async () => {
    vi.mocked(caseApi.getCourtFilingInfo).mockResolvedValue({
      ...defaultFilingInfo, court_name: '法院', our_party_is_plaintiff_side: false,
    })
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText(/我方当事人为被告/)
  })

  it('shows no credential hint', async () => {
    vi.mocked(caseApi.getCourtFilingInfo).mockResolvedValue({
      ...defaultFilingInfo, court_name: '法院', has_court_credential: false,
    })
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText(/没有一张网账号密码/)
  })

  it('executes filing on button click', async () => {
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('开始一张网立案')
    fireEvent.click(screen.getByText('开始一张网立案'))
    await screen.findByText(/立案成功/)
    expect(caseApi.executeCourtFiling).toHaveBeenCalled()
  })

  it('shows timing after execution', async () => {
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('开始一张网立案')
    fireEvent.click(screen.getByText('开始一张网立案'))
    await screen.findByText('耗时统计')
    expect(screen.getByText('总耗时：')).toBeInTheDocument()
  })

  it('handles execution error', async () => {
    vi.mocked(caseApi.executeCourtFiling).mockRejectedValue(new Error('fail'))
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('开始一张网立案')
    fireEvent.click(screen.getByText('开始一张网立案'))
    await screen.findByText(/启动立案失败/)
  })

  it('shows execution failure result', async () => {
    vi.mocked(caseApi.executeCourtFiling).mockResolvedValue({
      success: false, message: '立案失败原因', status: 'failed',
      session_id: null, timing: null,
    })
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('开始一张网立案')
    fireEvent.click(screen.getByText('开始一张网立案'))
    await screen.findByText(/立案失败原因/)
  })

  it('handles API load error silently', async () => {
    vi.mocked(caseApi.getCourtFilingInfo).mockRejectedValue(new Error('fail'))
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('法院一张网在线立案')
    expect(screen.getByText('法院一张网在线立案')).toBeInTheDocument()
  })

  it('shows loading info state', async () => {
    vi.mocked(caseApi.getCourtFilingInfo).mockReturnValue(new Promise(() => {}))
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('shows no material slots when none present', async () => {
    vi.mocked(caseApi.getCourtFilingInfo).mockResolvedValue({
      ...defaultFilingInfo, material_slots: [],
    })
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('法院一张网在线立案')
    expect(screen.queryByText('材料匹配')).not.toBeInTheDocument()
  })

  it('shows courtName from caseData when filingInfo has none', async () => {
    vi.mocked(caseApi.getCourtFilingInfo).mockResolvedValue({
      ...defaultFilingInfo, court_name: '',
    })
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    // courtName comes from supervising_authorities
    await screen.findByText(/管辖法院/)
  })

  it('uses api engine by default when has_http_plugin', async () => {
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText(/立案引擎/)
    expect(screen.getByText(/HTTP主链路/)).toBeInTheDocument()
  })

  it('shows playwright as default when no http plugin', async () => {
    vi.mocked(caseApi.getCourtFilingInfo).mockResolvedValue({
      ...defaultFilingInfo, has_http_plugin: false,
    })
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText(/立案引擎/)
    expect(screen.getByText(/Playwright/)).toBeInTheDocument()
  })

  it('handles execution with session polling', async () => {
    vi.mocked(caseApi.executeCourtFiling).mockResolvedValue({
      success: true, message: '处理中', status: 'in_progress',
      session_id: 'sess-123', timing: null,
    })
    vi.mocked(caseApi.getCourtFilingSession).mockResolvedValue({
      success: true, message: '完成', status: 'completed',
      timing: { overall_start: 0, overall_end: 5, login_end: 1 },
    } as any)
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('开始一张网立案')
    fireEvent.click(screen.getByText('开始一张网立案'))
    await screen.findByText(/处理中/)
  })
})
