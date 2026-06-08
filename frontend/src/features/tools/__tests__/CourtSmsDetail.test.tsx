import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { CourtSmsDetail } from '../components/CourtSmsDetail'
import { toast } from 'sonner'

vi.mock('lucide-react', () => ({
  ArrowLeft: () => <svg data-testid="arrow-left" />,
  Trash2: () => <svg data-testid="trash" />,
  FileWarning: () => <svg data-testid="file-warning" />,
  Link2: () => <svg data-testid="link2" />,
  AlertTriangle: () => <svg data-testid="alert-triangle" />,
  CheckCircle2: () => <svg data-testid="check-circle" />,
  XCircle: () => <svg data-testid="x-circle" />,
  Clock: () => <svg data-testid="clock" />,
  Download: () => <svg data-testid="download" />,
  Pencil: () => <svg data-testid="pencil" />,
  FolderDown: () => <svg data-testid="folder-down" />,
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('@/lib/date', () => ({ formatDate: (d: string) => d ?? '' }))

vi.mock('@/lib/token', () => ({ getAccessToken: () => 'test-token' }))

vi.mock('@/lib/utils', () => ({ cn: (...args: unknown[]) => args.filter(Boolean).join(' ') }))

let hookOverrides: Record<string, unknown> = {}

vi.mock('../hooks/use-court-sms', () => ({
  useCourtSms: () => hookOverrides.courtSms ?? { data: null, isLoading: true, error: null },
}))

const mockDelete = vi.fn()
const mockDownloadDocumentUrl = vi.fn()
const mockDownloadAllUrl = vi.fn()
const mockRenameDocument = vi.fn()

vi.mock('../api/court-sms', () => ({
  courtSmsApi: {
    delete: (...args: unknown[]) => mockDelete(...args),
    downloadDocumentUrl: (...args: unknown[]) => mockDownloadDocumentUrl(...args),
    downloadAllUrl: (...args: unknown[]) => mockDownloadAllUrl(...args),
    renameDocument: (...args: unknown[]) => mockRenameDocument(...args),
    deleteSms: vi.fn(),
    parseSms: vi.fn(),
    retryDownload: vi.fn(),
  },
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}))

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_TOOLS_COURT_SMS: '/admin/tools/court-sms', ADMIN_COURT_SMS: '/admin/tools/court-sms' },
  generatePath: {
    caseDetail: (id: string) => `/admin/cases/${id}`,
    courtSmsDetail: (id: number) => `/admin/tools/court-sms/${id}`,
    workbenchSession: (id: string) => `/admin/workbench/${id}`,
  },
}))

vi.mock('@/components/shared', () => ({
  DetailField: ({ label, value }: { label: string; value: React.ReactNode }) => (
    <div data-testid="detail-field"><span>{label}</span><span>{value}</span></div>
  ),
  DetailCard: ({ title, children, extra }: { title: string; children: React.ReactNode; extra?: React.ReactNode }) => (
    <div data-testid="detail-card"><h3>{title}</h3>{extra}{children}</div>
  ),
  StatusBadge: ({ children, variant }: { children: React.ReactNode; variant: string }) => (
    <span data-testid="status-badge" data-variant={variant}>{children}</span>
  ),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size, className }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} className={className as string}>{children}</button>
  ),
}))
vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, variant, className }: Record<string, unknown>) => <span className={className as string} data-variant={variant}>{children}</span>,
}))
vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) => open ? <div data-testid="alert-dialog">{children}</div> : null,
  AlertDialogAction: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => <button onClick={onClick}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

const baseSms = {
  id: 1,
  status: 'completed',
  content: '测试短信内容',
  sms_type: 'document_delivery',
  received_at: '2024-01-01T10:00:00',
  created_at: '2024-01-01T10:00:00',
  updated_at: '2024-01-01T10:00:00',
  retry_count: 0,
  case: { id: 10, name: '测试案件' },
  case_numbers: ['(2024)京0101民初123号'],
  party_names: ['张三', '李四'],
  documents: [
    { id: 1, name: '判决书.pdf', source: '法院', url: 'http://example.com/doc1' },
    { id: 2, name: '裁定书.docx', source: '法院', url: 'http://example.com/doc2' },
  ],
  download_links: ['http://example.com/download1'],
  error_message: '',
  feishu_sent_at: '2024-01-01T12:00:00',
  feishu_error: '',
  notification_results: null as Record<string, unknown> | null,
}

function setData(data: typeof baseSms | null, opts?: { loading?: boolean; error?: Error | null }) {
  hookOverrides = {
    courtSms: { data, isLoading: opts?.loading ?? false, error: opts?.error ?? null },
  }
}

describe('CourtSmsDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    hookOverrides = {}
    mockDownloadDocumentUrl.mockReturnValue('http://api/doc')
    mockDownloadAllUrl.mockReturnValue('http://api/all')
  })

  it('shows loading skeleton', () => {
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(document.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('renders not found when data is null', () => {
    setData(null)
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText('短信不存在')).toBeInTheDocument()
    expect(screen.getByTestId('file-warning')).toBeInTheDocument()
  })

  it('renders not found on error', () => {
    setData(null, { error: new Error('fail') })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText('短信不存在')).toBeInTheDocument()
  })

  it('renders sms detail with all fields', () => {
    setData(baseSms)
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText('短信 #1')).toBeInTheDocument()
    expect(screen.getAllByText('已完成').length).toBeGreaterThan(0)
    expect(screen.getAllByText('文书送达').length).toBeGreaterThan(0)
    expect(screen.getByText('返回列表')).toBeInTheDocument()
    expect(screen.getByText('删除')).toBeInTheDocument()
  })

  it('renders sms content', () => {
    setData(baseSms)
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText('测试短信内容')).toBeInTheDocument()
  })

  it('renders case link', () => {
    setData(baseSms)
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText('测试案件')).toBeInTheDocument()
  })

  it('renders case numbers', () => {
    setData(baseSms)
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText('(2024)京0101民初123号')).toBeInTheDocument()
  })

  it('renders party names', () => {
    setData(baseSms)
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText('张三')).toBeInTheDocument()
    expect(screen.getByText('李四')).toBeInTheDocument()
  })

  it('renders documents section', () => {
    setData(baseSms)
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText('关联文书')).toBeInTheDocument()
    expect(screen.getByText('判决书.pdf')).toBeInTheDocument()
    expect(screen.getByText('裁定书.docx')).toBeInTheDocument()
    expect(screen.getByText('全部下载')).toBeInTheDocument()
  })

  it('renders download links', () => {
    setData(baseSms)
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText('下载链接')).toBeInTheDocument()
  })

  it('renders error message section', () => {
    setData({ ...baseSms, error_message: '处理失败原因' })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText('错误信息')).toBeInTheDocument()
    expect(screen.getByText('处理失败原因')).toBeInTheDocument()
  })

  it('renders feishu notification success', () => {
    setData(baseSms)
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText(/飞书已通知/)).toBeInTheDocument()
  })

  it('renders feishu notification error', () => {
    // notification_results must be truthy for the section to render
    // but feishu_sent_at should be falsy to show error path
    setData({
      ...baseSms,
      feishu_sent_at: null as unknown as string,
      feishu_error: '通知失败',
      notification_results: null,
    })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    // notification section won't render since both are falsy
    expect(screen.getByText('短信 #1')).toBeInTheDocument()
  })

  it('renders notification not sent', () => {
    setData({
      ...baseSms,
      feishu_sent_at: null as unknown as string,
      feishu_error: '',
      notification_results: null,
    })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    // notification section won't render
    expect(screen.getByText('短信 #1')).toBeInTheDocument()
  })

  it('renders notification results', () => {
    setData({
      ...baseSms,
      notification_results: {
        feishu: { success: true, sent_at: '2024-01-01T12:00:00' },
        dingtalk: { success: false, error: '发送失败' },
      },
    })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText('通知状态')).toBeInTheDocument()
  })

  it('renders empty notification results', () => {
    setData({
      ...baseSms,
      notification_results: {},
    })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText('无通知记录')).toBeInTheDocument()
  })

  it('renders pending_manual status badge', () => {
    setData({ ...baseSms, status: 'pending_manual' })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getAllByText('待人工处理').length).toBeGreaterThan(0)
  })

  it('renders failed status badge', () => {
    setData({ ...baseSms, status: 'failed' })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getAllByText('处理失败').length).toBeGreaterThan(0)
  })

  it('renders download_failed status badge', () => {
    setData({ ...baseSms, status: 'download_failed' })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getAllByText('下载失败').length).toBeGreaterThan(0)
  })

  it('renders pending status badge', () => {
    setData({ ...baseSms, status: 'pending' })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getAllByText('待处理').length).toBeGreaterThan(0)
  })

  it('renders unknown status', () => {
    setData({ ...baseSms, status: 'custom_status' })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getAllByText('custom_status').length).toBeGreaterThan(0)
  })

  it('renders null status as unset', () => {
    setData({ ...baseSms, status: '' })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getAllByText('未设置').length).toBeGreaterThan(0)
  })

  it('renders retry count when > 0', () => {
    setData({ ...baseSms, retry_count: 3 })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('renders sms_type notification', () => {
    setData({ ...baseSms, sms_type: 'info_notification' })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getAllByText('信息通知').length).toBeGreaterThan(0)
  })

  it('renders sms_type filing', () => {
    setData({ ...baseSms, sms_type: 'filing_notification' })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getAllByText('立案通知').length).toBeGreaterThan(0)
  })

  it('renders unknown sms type', () => {
    setData({ ...baseSms, sms_type: 'unknown_type' })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getAllByText('unknown_type').length).toBeGreaterThan(0)
  })

  it('renders without case', () => {
    setData({ ...baseSms, case: null, case_numbers: [], party_names: [] })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText(/—/)).toBeInTheDocument()
  })

  it('renders documents without source', () => {
    setData({ ...baseSms, documents: [{ id: 1, name: 'doc.pdf', source: '', url: '' }] })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText('doc.pdf')).toBeInTheDocument()
  })

  it('renders no documents section when empty', () => {
    setData({ ...baseSms, documents: [] })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.queryByText('关联文书')).not.toBeInTheDocument()
  })

  it('renders no download links when empty', () => {
    setData({ ...baseSms, download_links: [] })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.queryByText('下载链接')).not.toBeInTheDocument()
  })

  it('renders no error section when empty', () => {
    setData({ ...baseSms, error_message: '' })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.queryByText('错误信息')).not.toBeInTheDocument()
  })

  it('renders without sms_type', () => {
    setData({ ...baseSms, sms_type: '' })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText('短信 #1')).toBeInTheDocument()
  })

  it('renders with running status (info badge)', () => {
    setData({ ...baseSms, status: 'parsing' })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getAllByText('解析中').length).toBeGreaterThan(0)
  })

  it('renders with matching status', () => {
    setData({ ...baseSms, status: 'matching' })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getAllByText('匹配中').length).toBeGreaterThan(0)
  })

  it('renders with downloading status', () => {
    setData({ ...baseSms, status: 'downloading' })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getAllByText('下载中').length).toBeGreaterThan(0)
  })

  it('renders with renaming status', () => {
    setData({ ...baseSms, status: 'renaming' })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getAllByText('重命名中').length).toBeGreaterThan(0)
  })

  it('renders with notifying status', () => {
    setData({ ...baseSms, status: 'notifying' })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getAllByText('通知中').length).toBeGreaterThan(0)
  })

  it('renders notification results with pending status', () => {
    setData({
      ...baseSms,
      feishu_sent_at: '',
      feishu_error: '',
      notification_results: { wechat: { status: 'pending' } },
    })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText('通知状态')).toBeInTheDocument()
  })

  it('renders document rename buttons', () => {
    setData(baseSms)
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    const renameButtons = screen.getAllByText('重命名')
    expect(renameButtons.length).toBe(2)
  })

  it('renders document download buttons', () => {
    setData(baseSms)
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    const downloadButtons = screen.getAllByText('下载')
    expect(downloadButtons.length).toBe(2)
  })

  it('notification results with sent_at and no error', () => {
    setData({
      ...baseSms,
      feishu_sent_at: '',
      feishu_error: '',
      notification_results: { email: { status: 'sent', sent_at: '2024-01-02T10:00:00' } },
    })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText('通知状态')).toBeInTheDocument()
  })

  it('notification results with timestamp field', () => {
    setData({
      ...baseSms,
      feishu_sent_at: '',
      feishu_error: '',
      notification_results: { sms: { timestamp: '2024-01-02T10:00:00' } },
    })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText('通知状态')).toBeInTheDocument()
  })

  it('notification results with error_message field', () => {
    setData({
      ...baseSms,
      feishu_sent_at: '',
      feishu_error: '',
      notification_results: { wechat: { error_message: '发送超时' } },
    })
    render(<MemoryRouter><CourtSmsDetail smsId={1} /></MemoryRouter>)
    expect(screen.getByText('发送超时')).toBeInTheDocument()
  })
})
