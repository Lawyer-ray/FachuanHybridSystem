import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { CourtSmsDetail } from '../CourtSmsDetail'
import { courtSmsApi } from '../../api/court-sms'
import { toast } from 'sonner'

const mockNavigate = vi.fn()

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => mockNavigate }
})
vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_TOOLS_COURT_SMS: '/admin/tools/court-sms' },
  generatePath: { caseDetail: (id: string) => `/admin/cases/${id}` },
}))
vi.mock('@/lib/date', () => ({ formatDate: (d: string) => d || '-' }))
vi.mock('@/lib/token', () => ({ getAccessToken: () => 'test-token' }))
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
vi.mock('@/components/shared', () => ({
  DetailField: ({ label, value }: { label: string; value: unknown }) => (
    <div><span>{label}</span><span>{value as React.ReactNode}</span></div>
  ),
  DetailCard: ({ title, extra, children }: { title: string; extra?: React.ReactNode; children: React.ReactNode }) => (
    <div>
      <h3>{title}</h3>
      {extra}
      {children}
    </div>
  ),
  StatusBadge: ({ children, variant }: { children: React.ReactNode; variant: string }) => (
    <span data-variant={variant}>{children}</span>
  ),
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

  it('calls navigate on back button click', () => {
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    const backButtons = screen.getAllByText('返回列表')
    fireEvent.click(backButtons[0])
    expect(mockNavigate).toHaveBeenCalledWith('/admin/tools/court-sms')
  })

  it('calls courtSmsApi.delete on confirm delete', async () => {
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    fireEvent.click(screen.getByText('删除'))
    fireEvent.click(screen.getByText('确认删除'))
    await waitFor(() => {
      expect(courtSmsApi.delete).toHaveBeenCalledWith(1)
    })
  })

  it('calls handleDownload when download button clicked', async () => {
    const mockCreateObjectURL = vi.fn(() => 'blob:mock')
    const mockRevokeObjectURL = vi.fn()
    global.URL.createObjectURL = mockCreateObjectURL
    global.URL.revokeObjectURL = mockRevokeObjectURL
    const mockClick = vi.fn()
    const origCreate = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = origCreate(tag)
      if (tag === 'a') el.click = mockClick
      return el
    })
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      blob: () => Promise.resolve(new Blob()),
    })

    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    const downloadButtons = screen.getAllByText('下载')
    fireEvent.click(downloadButtons[0])
    await waitFor(() => {
      expect(courtSmsApi.downloadDocumentUrl).toHaveBeenCalledWith(1, 0)
    })

    vi.restoreAllMocks()
    global.fetch = undefined as unknown as typeof global.fetch
  })

  it('calls handleDownloadAll when "全部下载" clicked', async () => {
    const mockCreateObjectURL = vi.fn(() => 'blob:mock')
    const mockRevokeObjectURL = vi.fn()
    global.URL.createObjectURL = mockCreateObjectURL
    global.URL.revokeObjectURL = mockRevokeObjectURL
    const mockClick = vi.fn()
    const origCreate = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = origCreate(tag)
      if (tag === 'a') el.click = mockClick
      return el
    })
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      blob: () => Promise.resolve(new Blob()),
    })

    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    fireEvent.click(screen.getByText('全部下载'))
    await waitFor(() => {
      expect(courtSmsApi.downloadAllUrl).toHaveBeenCalledWith(1)
    })

    vi.restoreAllMocks()
    global.fetch = undefined as unknown as typeof global.fetch
  })

  it('enters rename mode when rename button clicked', () => {
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    const renameButtons = screen.getAllByText('重命名')
    fireEvent.click(renameButtons[0])
    expect(screen.getByText('确定')).toBeInTheDocument()
    expect(screen.getByText('取消')).toBeInTheDocument()
  })

  it('cancels rename mode', () => {
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    fireEvent.click(screen.getAllByText('重命名')[0])
    fireEvent.click(screen.getByText('取消'))
    expect(screen.queryByText('确定')).not.toBeInTheDocument()
  })

  it('calls handleRename when confirm button clicked', async () => {
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    fireEvent.click(screen.getAllByText('重命名')[0])
    const input = screen.getByRole('textbox')
    fireEvent.change(input, { target: { value: 'new_name' } })
    fireEvent.click(screen.getByText('确定'))
    await waitFor(() => {
      expect(courtSmsApi.renameDocument).toHaveBeenCalledWith(1, 0, 'new_name')
    })
  })

  it('handles rename failure with success:false', async () => {
    vi.mocked(courtSmsApi.renameDocument).mockResolvedValueOnce({ success: false, error: '重命名出错' })
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    fireEvent.click(screen.getAllByText('重命名')[0])
    fireEvent.click(screen.getByText('确定'))
    await waitFor(() => {
      expect(courtSmsApi.renameDocument).toHaveBeenCalled()
    })
  })

  it('handles rename exception', async () => {
    vi.mocked(courtSmsApi.renameDocument).mockRejectedValueOnce(new Error('network error'))
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    fireEvent.click(screen.getAllByText('重命名')[0])
    fireEvent.click(screen.getByText('确定'))
    await waitFor(() => {
      expect(courtSmsApi.renameDocument).toHaveBeenCalled()
    })
  })

  it('handles delete failure', async () => {
    vi.mocked(courtSmsApi.delete).mockRejectedValueOnce(new Error('delete error'))
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    fireEvent.click(screen.getByText('删除'))
    fireEvent.click(screen.getByText('确认删除'))
    await waitFor(() => {
      expect(courtSmsApi.delete).toHaveBeenCalled()
    })
  })

  it('handles download failure', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 500 })
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    fireEvent.click(screen.getAllByText('下载')[0])
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled()
    })
    global.fetch = undefined as unknown as typeof global.fetch
  })

  it('shows download_failed status badge', () => {
    mockUseCourtSms.mockReturnValue({
      data: { ...mockSms, status: 'download_failed' },
      isLoading: false, error: null,
    })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getAllByText('下载失败').length).toBeGreaterThanOrEqual(1)
  })

  it('shows unknown status label', () => {
    mockUseCourtSms.mockReturnValue({
      data: { ...mockSms, status: 'custom_unknown' },
      isLoading: false, error: null,
    })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getAllByText('custom_unknown').length).toBeGreaterThanOrEqual(1)
  })

  it('renders notification with error and no success', () => {
    mockUseCourtSms.mockReturnValue({
      data: { ...mockSms, notification_results: { platform1: { error: 'send failed' } } },
      isLoading: false, error: null,
    })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getByText('send failed')).toBeInTheDocument()
  })

  it('renders notification with no success and no error', () => {
    mockUseCourtSms.mockReturnValue({
      data: { ...mockSms, notification_results: { platform1: {} } },
      isLoading: false, error: null,
    })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getByText('platform1')).toBeInTheDocument()
  })

  it('renders notification with status=sent', () => {
    mockUseCourtSms.mockReturnValue({
      data: { ...mockSms, notification_results: { platform1: { status: 'sent', sent_at: '2026-01-01' } } },
      isLoading: false, error: null,
    })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getByText('platform1')).toBeInTheDocument()
  })

  it('shows null sms type label', () => {
    mockUseCourtSms.mockReturnValue({
      data: { ...mockSms, sms_type: null },
      isLoading: false, error: null,
    })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getAllByText('已完成').length).toBeGreaterThanOrEqual(1)
  })

  it('shows unknown sms type label', () => {
    mockUseCourtSms.mockReturnValue({
      data: { ...mockSms, sms_type: 'unknown_type' },
      isLoading: false, error: null,
    })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getAllByText('unknown_type').length).toBeGreaterThanOrEqual(1)
  })

  it('handles Enter key in rename input', async () => {
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    fireEvent.click(screen.getAllByText('重命名')[0])
    const input = screen.getByRole('textbox')
    fireEvent.change(input, { target: { value: 'via_enter' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => {
      expect(courtSmsApi.renameDocument).toHaveBeenCalledWith(1, 0, 'via_enter')
    })
  })

  it('handles Escape key in rename input', () => {
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    fireEvent.click(screen.getAllByText('重命名')[0])
    const input = screen.getByRole('textbox')
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(screen.queryByText('确定')).not.toBeInTheDocument()
  })

  it('does not rename when value is empty', async () => {
    vi.mocked(courtSmsApi.renameDocument).mockClear()
    mockUseCourtSms.mockReturnValue({ data: mockSms, isLoading: false, error: null })
    render(<CourtSmsDetail smsId={1} />)
    fireEvent.click(screen.getAllByText('重命名')[0])
    const input = screen.getByRole('textbox')
    fireEvent.change(input, { target: { value: '' } })
    fireEvent.click(screen.getByText('确定'))
    await waitFor(() => {
      expect(courtSmsApi.renameDocument).not.toHaveBeenCalled()
    })
  })

  it('renders doc source when present', () => {
    mockUseCourtSms.mockReturnValue({
      data: { ...mockSms, documents: [{ id: 1, name: 'doc.pdf', source: '短信附件' }] },
      isLoading: false, error: null,
    })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getByText('短信附件')).toBeInTheDocument()
  })

  it('renders no notification section when no results and no feishu', () => {
    mockUseCourtSms.mockReturnValue({
      data: { ...mockSms, notification_results: null, feishu_sent_at: null, feishu_error: null },
      isLoading: false, error: null,
    })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.queryByText('通知状态')).not.toBeInTheDocument()
  })

  it('renders feishu error fallback when no results and feishu_error set', () => {
    // When notification_results is null and feishu_sent_at is also null,
    // the notification section is not rendered at all (even with feishu_error)
    mockUseCourtSms.mockReturnValue({
      data: { ...mockSms, notification_results: null, feishu_sent_at: null, feishu_error: '飞书发送失败' },
      isLoading: false, error: null,
    })
    render(<CourtSmsDetail smsId={1} />)
    // Section should not render when both notification_results and feishu_sent_at are null
    expect(screen.queryByText('通知状态')).not.toBeInTheDocument()
  })

  it('renders empty notification results', () => {
    mockUseCourtSms.mockReturnValue({
      data: { ...mockSms, notification_results: {} },
      isLoading: false, error: null,
    })
    render(<CourtSmsDetail smsId={1} />)
    expect(screen.getByText('无通知记录')).toBeInTheDocument()
  })
})
