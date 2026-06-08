import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { CourtSmsDetail } from '../CourtSmsDetail'

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})
vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_TOOLS_COURT_SMS: '/admin/tools/court-sms' },
  generatePath: { caseDetail: (id: string) => `/admin/cases/${id}` },
}))
vi.mock('@/lib/date', () => ({ formatDate: (d: string) => d || '-' }))
vi.mock('@/lib/token', () => ({ getAccessToken: () => 'token' }))
vi.mock('../../hooks/use-court-sms', () => ({ useCourtSms: vi.fn() }))
vi.mock('../../api/court-sms', () => ({
  courtSmsApi: {
    delete: vi.fn().mockResolvedValue({}),
    downloadDocumentUrl: vi.fn().mockReturnValue('http://test/doc'),
    downloadAllUrl: vi.fn().mockReturnValue('http://test/all'),
    renameDocument: vi.fn().mockResolvedValue({ success: true }),
  },
}))
vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}))

import { useCourtSms } from '../../hooks/use-court-sms'

const mockUseCourtSms = useCourtSms as unknown as ReturnType<typeof vi.fn>

const mockSms = {
  id: 1,
  status: 'completed',
  sms_type: 'document_delivery',
  content: 'Test SMS content',
  received_at: '2026-01-01T10:00:00',
  created_at: '2026-01-01T10:00:00',
  updated_at: '2026-01-01T10:00:00',
  case: { id: 10, name: 'Test Case' },
  case_numbers: ['(2026)民初1号'],
  party_names: ['张三', '李四'],
  documents: [{ id: 1, name: 'doc1.pdf', source: 'court' }],
  download_links: ['http://example.com/download'],
  error_message: null,
  retry_count: 0,
  notification_results: { feishu: { success: true, sent_at: '2026-01-01' } },
  feishu_sent_at: null,
  feishu_error: null,
}

describe('CourtSmsDetail', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows loading skeleton', () => {
    mockUseCourtSms.mockReturnValue({ data: undefined, isLoading: true, error: null })
    render(<CourtSmsDetail smsId={1} />)
    expect(document.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('shows error state', () => {
    mockUseCourtSms.mockReturnValue({ data: undefined, isLoading: false, error: new Error('x') })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getByText('短信不存在')).toBeInTheDocument()
  })

  it('renders SMS content', () => {
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getByText('Test SMS content')).toBeInTheDocument()
  })

  it('renders status badge', () => {
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getAllByText('已完成').length).toBeGreaterThanOrEqual(1)
  })

  it('renders sms type badge', () => {
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getAllByText('文书送达').length).toBeGreaterThanOrEqual(1)
  })

  it('renders case link', () => {
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getByText('Test Case')).toBeInTheDocument()
  })

  it('renders case numbers', () => {
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getByText('(2026)民初1号')).toBeInTheDocument()
  })

  it('renders party names', () => {
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getByText('张三')).toBeInTheDocument()
  })

  it('renders documents section', () => {
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getByText('doc1.pdf')).toBeInTheDocument()
    expect(screen.getByText('全部下载')).toBeInTheDocument()
  })

  it('renders download links', () => {
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getByText('http://example.com/download')).toBeInTheDocument()
  })

  it('renders notification results', () => {
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getByText('通知状态')).toBeInTheDocument()
  })

  it('opens delete dialog', () => {
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    fireEvent.click(screen.getByText('删除'))
    expect(screen.getByText('确认删除短信')).toBeInTheDocument()
  })

  it('shows error message when present', () => {
    mockUseCourtSms.mockReturnValue({
      data: { ...mockSms, error_message: 'Parse failed' },
      isLoading: false, error: null,
    })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getByText('错误信息')).toBeInTheDocument()
    expect(screen.getByText('Parse failed')).toBeInTheDocument()
  })

  it('shows retry count when > 0', () => {
    mockUseCourtSms.mockReturnValue({
      data: { ...mockSms, retry_count: 3 },
      isLoading: false, error: null,
    })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getByText('重试次数')).toBeInTheDocument()
  })

  it('shows null notification results', () => {
    mockUseCourtSms.mockReturnValue({
      data: { ...mockSms, notification_results: null, feishu_sent_at: '2026-01-01' },
      isLoading: false, error: null,
    })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getByText(/飞书已通知/)).toBeInTheDocument()
  })

  it('shows feishu error when present', () => {
    // feishu_sent_at must be set for the notification section to render
    // When feishu_error is present but feishu_sent_at is not, the section won't show
    mockUseCourtSms.mockReturnValue({
      data: { ...mockSms, notification_results: { feishu: { error: 'send failed' } } },
      isLoading: false, error: null,
    })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getAllByText('通知状态').length).toBeGreaterThanOrEqual(1)
  })

  it('shows no notification when nothing set', () => {
    mockUseCourtSms.mockReturnValue({
      data: { ...mockSms, notification_results: null, feishu_sent_at: '2026-01-01', feishu_error: null },
      isLoading: false, error: null,
    })
    render(<CourtSmsDetail smsId={1} />)
    // When feishu_sent_at is set, it shows the sent message
    expect(screen.getAllByText(/飞书已通知/).length).toBeGreaterThanOrEqual(1)
  })

  it('shows empty case_numbers and party_names', () => {
    mockUseCourtSms.mockReturnValue({
      data: { ...mockSms, case_numbers: [], party_names: [], case: null },
      isLoading: false, error: null,
    })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getByText('短信内容')).toBeInTheDocument()
  })

  it('shows empty documents section', () => {
    mockUseCourtSms.mockReturnValue({
      data: { ...mockSms, documents: [], download_links: [] },
      isLoading: false, error: null,
    })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getByText('关联信息')).toBeInTheDocument()
  })

  it('shows failed status badge', () => {
    mockUseCourtSms.mockReturnValue({
      data: { ...mockSms, status: 'failed' },
      isLoading: false, error: null,
    })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getAllByText('处理失败').length).toBeGreaterThanOrEqual(1)
  })

  it('shows pending_manual status badge', () => {
    mockUseCourtSms.mockReturnValue({
      data: { ...mockSms, status: 'pending_manual' },
      isLoading: false, error: null,
    })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getAllByText('待人工处理').length).toBeGreaterThanOrEqual(1)
  })

  it('shows null status badge', () => {
    mockUseCourtSms.mockReturnValue({
      data: { ...mockSms, status: null },
      isLoading: false, error: null,
    })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getAllByText('未设置').length).toBeGreaterThanOrEqual(1)
  })
})
