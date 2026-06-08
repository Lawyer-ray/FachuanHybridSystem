import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { CourtSmsTool } from '../CourtSmsTool'

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})
vi.mock('@/routes/paths', () => ({
  generatePath: { courtSmsDetail: (id: number) => `/admin/tools/court-sms/${id}` },
}))
vi.mock('@/lib/date', () => ({ formatDate: (d: string) => d || '-' }))
vi.mock('../../hooks/use-court-sms', () => ({
  useCourtSmsList: vi.fn().mockReturnValue({ data: { items: [] }, isLoading: false }),
}))
vi.mock('../../api/court-sms', () => ({
  courtSmsApi: {
    deleteBatch: vi.fn().mockResolvedValue({}),
    submit: vi.fn().mockResolvedValue({}),
    assignCase: vi.fn().mockResolvedValue({}),
  },
}))
vi.mock('@/features/cases/api', () => ({
  caseApi: { search: vi.fn().mockResolvedValue([]) },
}))
vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useQuery: vi.fn().mockReturnValue({ data: [], isFetching: false }),
}))

import { useCourtSmsList } from '../../hooks/use-court-sms'

const mockUseCourtSmsList = useCourtSmsList as unknown as ReturnType<typeof vi.fn>

const mockItems = [
  { id: 1, status: 'completed', content: 'SMS 1', case_name: 'Case A', has_documents: true, received_at: '2026-01-01T10:00:00', sms_type: 'document_delivery' },
  { id: 2, status: 'pending_manual', content: 'SMS 2', case_name: null, has_documents: false, received_at: '2026-01-02T10:00:00', sms_type: null },
  { id: 3, status: 'failed', content: 'SMS 3', case_name: null, has_documents: false, received_at: '2026-01-03T10:00:00', sms_type: 'info_notification' },
]

describe('CourtSmsTool', () => {
  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()
    mockUseCourtSmsList.mockReturnValue({ data: { items: mockItems }, isLoading: false })
  })

  it('renders header', () => {
    render(<CourtSmsTool />)
    expect(screen.getByText('法院短信')).toBeInTheDocument()
  })

  it('renders submit button', () => {
    render(<CourtSmsTool />)
    expect(screen.getByText('提交短信')).toBeInTheDocument()
  })

  it('renders filter buttons', () => {
    render(<CourtSmsTool />)
    expect(screen.getByText('全部')).toBeInTheDocument()
    expect(screen.getAllByText('已完成').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('待人工处理').length).toBeGreaterThanOrEqual(1)
  })

  it('renders search input', () => {
    render(<CourtSmsTool />)
    expect(screen.getByPlaceholderText('搜索内容或案件名称...')).toBeInTheDocument()
  })

  it('renders table with items', () => {
    render(<CourtSmsTool />)
    expect(screen.getByText('SMS 1')).toBeInTheDocument()
    expect(screen.getByText('SMS 2')).toBeInTheDocument()
  })

  it('shows loading state', () => {
    mockUseCourtSmsList.mockReturnValue({ data: undefined, isLoading: true })
    render(<CourtSmsTool />)
    expect(document.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('shows empty state', () => {
    mockUseCourtSmsList.mockReturnValue({ data: { items: [] }, isLoading: false })
    render(<CourtSmsTool />)
    expect(screen.getByText('没有短信记录')).toBeInTheDocument()
  })

  it('opens submit dialog', () => {
    render(<CourtSmsTool />)
    fireEvent.click(screen.getByText('提交短信'))
    // Dialog should open - check for the textarea placeholder
    expect(screen.getByPlaceholderText('粘贴短信内容...')).toBeInTheDocument()
  })

  it('renders manual assign button for pending_manual items', () => {
    render(<CourtSmsTool />)
    expect(screen.getByText('手动关联')).toBeInTheDocument()
  })

  it('renders status badges', () => {
    render(<CourtSmsTool />)
    expect(screen.getAllByText('已完成').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('处理失败').length).toBeGreaterThanOrEqual(1)
  })

  it('filters by search text', () => {
    render(<CourtSmsTool />)
    fireEvent.change(screen.getByPlaceholderText('搜索内容或案件名称...'), { target: { value: 'SMS 1' } })
    expect(screen.getByText('SMS 1')).toBeInTheDocument()
  })

  it('renders date filters', () => {
    render(<CourtSmsTool />)
    expect(screen.getByLabelText('从')).toBeInTheDocument()
    expect(screen.getByLabelText('至')).toBeInTheDocument()
  })

  it('shows has_documents column', () => {
    render(<CourtSmsTool />)
    expect(screen.getByText('有')).toBeInTheDocument()
  })

  it('renders sms type filter', () => {
    render(<CourtSmsTool />)
    expect(screen.getByText('全部类型')).toBeInTheDocument()
  })

  it('renders batch delete bar when items selected', () => {
    render(<CourtSmsTool />)
    // Select an item by clicking the checkbox
    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[1]) // first non-header checkbox
    expect(screen.getByText(/已选/)).toBeInTheDocument()
    expect(screen.getByText('删除选中')).toBeInTheDocument()
  })

  it('renders select all checkbox', () => {
    render(<CourtSmsTool />)
    expect(screen.getByLabelText('全选')).toBeInTheDocument()
  })

  it('toggles select all', () => {
    render(<CourtSmsTool />)
    const selectAll = screen.getByLabelText('全选')
    fireEvent.click(selectAll)
    expect(screen.getByText(/已选/)).toBeInTheDocument()
  })

  it('renders content column as clickable', () => {
    render(<CourtSmsTool />)
    const contentCell = screen.getByText('SMS 1')
    expect(contentCell.closest('[class*="cursor-pointer"]')).toBeTruthy()
  })
})
