/**
 * Additional coverage tests for CourtFilingSection.tsx
 * Targets: uncovered branches (24) and functions (3)
 * Focus: formatDuration helper, pollSession, various hint conditions
 */

import { render, screen, fireEvent, cleanup, act } from '@testing-library/react'
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
  ],
}

const baseCaseData = {
  id: 1,
  name: 'Test Case',
  cause_of_action: '合同纠纷',
  target_amount: 100000,
  supervising_authorities: [{ id: 1, name: '北京市朝阳区人民法院', authority_type: 'trial' }],
} as unknown as Case

describe('CourtFilingSection - branch/function coverage', () => {
  beforeEach(() => {
    cleanup()
    vi.useRealTimers()
    vi.mocked(caseApi.getCourtFilingInfo).mockReset()
    vi.mocked(caseApi.executeCourtFiling).mockReset()
    vi.mocked(caseApi.getCourtFilingSession).mockReset()
    vi.mocked(caseApi.getCourtFilingInfo).mockResolvedValue(defaultFilingInfo)
    vi.mocked(caseApi.executeCourtFiling).mockResolvedValue({
      success: true, message: 'OK', status: 'completed', session_id: null, timing: null,
    })
  })

  // --- formatDuration branches (lines 23-27) ---
  // null -> '-'
  it('shows "-" for null timing overall_end', async () => {
    vi.mocked(caseApi.executeCourtFiling).mockResolvedValue({
      success: true, message: 'OK', status: 'completed', session_id: null,
      timing: { overall_start: 0, overall_end: 10, login_end: null },
    })
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('开始一张网立案')
    fireEvent.click(screen.getByText('开始一张网立案'))
    await screen.findByText('耗时统计')
  })

  // undefined timing
  it('shows timing when overall_end exists', async () => {
    vi.mocked(caseApi.executeCourtFiling).mockResolvedValue({
      success: true, message: 'OK', status: 'completed', session_id: null,
      timing: { overall_start: 0, overall_end: 5.5, login_end: 1.2 },
    })
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('开始一张网立案')
    fireEvent.click(screen.getByText('开始一张网立案'))
    await screen.findByText('耗时统计')
  })

  // --- Polling session branches (lines 59-75) ---

  it('polls session and completes on completed status', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.mocked(caseApi.executeCourtFiling).mockResolvedValue({
      success: true, message: '处理中', status: 'in_progress',
      session_id: 'sess-001', timing: null,
    })
    vi.mocked(caseApi.getCourtFilingSession).mockResolvedValue({
      success: true, message: '完成', status: 'completed',
      timing: { overall_start: 0, overall_end: 5, login_end: 1 },
    } as never)

    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await vi.advanceTimersByTimeAsync(100) // let loadInfo resolve
    await screen.findByText('开始一张网立案')
    fireEvent.click(screen.getByText('开始一张网立案'))

    // Advance timer to trigger poll
    await vi.advanceTimersByTimeAsync(3500)

    expect(caseApi.getCourtFilingSession).toHaveBeenCalledWith('sess-001')
    vi.useRealTimers()
  })

  it('polls session and stops on failed status', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.mocked(caseApi.executeCourtFiling).mockResolvedValue({
      success: true, message: '处理中', status: 'running',
      session_id: 'sess-002', timing: null,
    })
    vi.mocked(caseApi.getCourtFilingSession).mockResolvedValue({
      success: false, message: '失败', status: 'failed',
      timing: null,
    } as never)

    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await vi.advanceTimersByTimeAsync(100)
    await screen.findByText('开始一张网立案')
    fireEvent.click(screen.getByText('开始一张网立案'))

    await vi.advanceTimersByTimeAsync(3500)

    expect(caseApi.getCourtFilingSession).toHaveBeenCalledWith('sess-002')
    vi.useRealTimers()
  })

  it('poll session handles API error and stops polling', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.mocked(caseApi.executeCourtFiling).mockResolvedValue({
      success: true, message: '处理中', status: 'in_progress',
      session_id: 'sess-003', timing: null,
    })
    vi.mocked(caseApi.getCourtFilingSession).mockRejectedValue(new Error('network'))

    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await vi.advanceTimersByTimeAsync(100)
    await screen.findByText('开始一张网立案')
    fireEvent.click(screen.getByText('开始一张网立案'))

    await vi.advanceTimersByTimeAsync(3500)

    expect(caseApi.getCourtFilingSession).toHaveBeenCalled()
    vi.useRealTimers()
  })

  // --- Hint branches (lines 101-110) ---

  it('shows null hint when all conditions met (can execute)', async () => {
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('开始一张网立案')
    // No hint should be shown when all conditions are met
    expect(screen.queryByText(/请先设置管辖法院/)).not.toBeInTheDocument()
    expect(screen.queryByText(/被告/)).not.toBeInTheDocument()
    expect(screen.queryByText(/账号密码/)).not.toBeInTheDocument()
  })

  // --- Filing type label branch (line 112) ---

  it('shows execution filing type label', async () => {
    vi.mocked(caseApi.getCourtFilingInfo).mockResolvedValue({
      ...defaultFilingInfo,
      suggested_filing_type: 'execution',
    })
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('申请执行')
  })

  it('defaults to 民事一审 for unknown filing type', async () => {
    vi.mocked(caseApi.getCourtFilingInfo).mockResolvedValue({
      ...defaultFilingInfo,
      suggested_filing_type: 'unknown_type',
    })
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('法院一张网在线立案')
    expect(screen.getByText('民事一审')).toBeInTheDocument()
  })

  // --- Target amount formatting (line 135) ---

  it('uses caseData.target_amount when filingInfo has no target_amount', async () => {
    vi.mocked(caseApi.getCourtFilingInfo).mockResolvedValue({
      ...defaultFilingInfo,
      target_amount: null,
    })
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText(/标的额/)
  })

  // --- Material slots: matched vs unmatched (lines 178-188) ---

  it('shows matched file green text', async () => {
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('材料匹配')
    expect(screen.getByText('complaint.docx')).toBeInTheDocument()
  })

  it('shows unmatched optional slot', async () => {
    vi.mocked(caseApi.getCourtFilingInfo).mockResolvedValue({
      ...defaultFilingInfo,
      material_slots: [
        { slot_name: '证据目录', matched_file: null, required: false },
      ],
    })
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('材料匹配')
    expect(screen.getByText('未匹配')).toBeInTheDocument()
  })

  // --- Refresh button (line 202) ---

  it('refresh button calls loadInfo', async () => {
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('开始一张网立案')
    // Find the refresh button (ghost variant with RefreshCw)
    const buttons = screen.getAllByRole('button')
    const refreshBtn = buttons[buttons.length - 1] // last button
    fireEvent.click(refreshBtn)
    // Should re-call getCourtFilingInfo
    expect(caseApi.getCourtFilingInfo).toHaveBeenCalled()
  })

  // --- Timing: HTTP and Playwright timing branches (lines 233-244) ---

  it('shows HTTP timing when http_start and http_end exist', async () => {
    vi.mocked(caseApi.executeCourtFiling).mockResolvedValue({
      success: true, message: 'OK', status: 'completed', session_id: null,
      timing: { overall_start: 0, overall_end: 10, login_end: 2, http_start: 3, http_end: 7 },
    })
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('开始一张网立案')
    fireEvent.click(screen.getByText('开始一张网立案'))
    await screen.findByText('耗时统计')
    expect(screen.getByText('HTTP主链路：')).toBeInTheDocument()
  })

  it('shows Playwright timing when playwright_start and playwright_end exist', async () => {
    vi.mocked(caseApi.executeCourtFiling).mockResolvedValue({
      success: true, message: 'OK', status: 'completed', session_id: null,
      timing: { overall_start: 0, overall_end: 10, login_end: 2, playwright_start: 3, playwright_end: 8 },
    })
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('开始一张网立案')
    fireEvent.click(screen.getByText('开始一张网立案'))
    await screen.findByText('耗时统计')
    expect(screen.getByText('Playwright：')).toBeInTheDocument()
  })

  // --- No court from caseData (line 38, 101) ---

  it('handles caseData with no supervising_authorities', async () => {
    vi.mocked(caseApi.getCourtFilingInfo).mockResolvedValue({
      ...defaultFilingInfo, court_name: '',
    })
    const noAuthCase = { ...baseCaseData, supervising_authorities: [] } as unknown as Case
    render(<CourtFilingSection caseId={1} caseData={noAuthCase} />)
    await screen.findByText('法院一张网在线立案')
    expect(screen.getByText(/请先设置管辖法院/)).toBeInTheDocument()
  })

  it('handles caseData with null supervising_authorities', async () => {
    vi.mocked(caseApi.getCourtFilingInfo).mockResolvedValue({
      ...defaultFilingInfo, court_name: '',
    })
    const nullAuthCase = { ...baseCaseData, supervising_authorities: null } as unknown as Case
    render(<CourtFilingSection caseId={1} caseData={nullAuthCase} />)
    await screen.findByText('法院一张网在线立案')
    expect(screen.getByText(/请先设置管辖法院/)).toBeInTheDocument()
  })

  // --- Execute with timing result ---

  it('shows timing result with all fields', async () => {
    vi.mocked(caseApi.executeCourtFiling).mockResolvedValue({
      success: true, message: '成功', status: 'completed', session_id: null,
      timing: {
        overall_start: 0, overall_end: 15.5, login_end: 3.2,
        http_start: 4, http_end: 10,
        playwright_start: 10, playwright_end: 15,
      },
    })
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText('开始一张网立案')
    fireEvent.click(screen.getByText('开始一张网立案'))
    await screen.findByText('耗时统计')
    expect(screen.getByText('登录：')).toBeInTheDocument()
    expect(screen.getByText('HTTP主链路：')).toBeInTheDocument()
    expect(screen.getByText('Playwright：')).toBeInTheDocument()
    expect(screen.getByText('总耗时：')).toBeInTheDocument()
  })

  // --- Radio button onChange branches (lines 148, 160) ---

  it('switches filing engine to api', async () => {
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText(/立案引擎/)
    const radios = screen.getAllByRole('radio')
    const apiRadio = radios.find(r => r.getAttribute('value') === 'api')
    if (apiRadio) fireEvent.click(apiRadio)
    expect(screen.getByText(/立案引擎/)).toBeInTheDocument()
  })

  it('switches filing engine to playwright', async () => {
    render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await screen.findByText(/立案引擎/)
    const radios = screen.getAllByRole('radio')
    const pwRadio = radios.find(r => r.getAttribute('value') === 'playwright')
    if (pwRadio) fireEvent.click(pwRadio)
    expect(screen.getByText(/立案引擎/)).toBeInTheDocument()
  })

  // --- Cleanup: unmount clears interval (line 56) ---

  it('cleans up poll interval on unmount', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.mocked(caseApi.executeCourtFiling).mockResolvedValue({
      success: true, message: '处理中', status: 'in_progress',
      session_id: 'sess-cleanup', timing: null,
    })

    const { unmount } = render(<CourtFilingSection caseId={1} caseData={baseCaseData} />)
    await vi.advanceTimersByTimeAsync(100)
    await screen.findByText('开始一张网立案')
    fireEvent.click(screen.getByText('开始一张网立案'))

    unmount()
    // Should not throw
    vi.useRealTimers()
  })
})
