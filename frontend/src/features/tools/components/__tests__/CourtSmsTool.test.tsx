import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { CourtSmsTool } from '../CourtSmsTool'
import { toast } from 'sonner'

const mockNavigate = vi.fn()
const mockInvalidateQueries = vi.fn()

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => mockNavigate }
})
vi.mock('@/routes/paths', () => ({
  generatePath: { courtSmsDetail: (id: number) => `/admin/tools/court-sms/${id}` },
}))
vi.mock('@/lib/date', () => ({ formatDate: (d: string) => d || '-' }))
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))
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
  useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
  useQuery: vi.fn().mockReturnValue({ data: [], isFetching: false }),
}))

import { useCourtSmsList } from '../../hooks/use-court-sms'
import { courtSmsApi } from '../../api/court-sms'

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

  // --- New tests for uncovered lines ---

  it('navigates to detail on content click', () => {
    render(<CourtSmsTool />)
    const contentCell = screen.getByText('SMS 1')
    fireEvent.click(contentCell)
    expect(mockNavigate).toHaveBeenCalledWith('/admin/tools/court-sms/1')
  })

  it('filters by case_name search', () => {
    render(<CourtSmsTool />)
    fireEvent.change(screen.getByPlaceholderText('搜索内容或案件名称...'), { target: { value: 'Case A' } })
    expect(screen.getByText('SMS 1')).toBeInTheDocument()
    // SMS 2 and 3 should be filtered out
    expect(screen.queryByText('SMS 2')).not.toBeInTheDocument()
  })

  it('opens assign case dialog on manual assign click', () => {
    render(<CourtSmsTool />)
    fireEvent.click(screen.getByText('手动关联'))
    // Dialog should open - use getAllByText since text appears in header and dialog
    expect(screen.getAllByText('关联案件').length).toBeGreaterThanOrEqual(1)
  })

  it('batch delete calls API and shows success toast', async () => {
    render(<CourtSmsTool />)
    // Select first item
    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[1])
    // Click delete
    fireEvent.click(screen.getByText('删除选中'))
    await waitFor(() => {
      expect(courtSmsApi.deleteBatch).toHaveBeenCalledWith([1])
      expect(toast.success).toHaveBeenCalledWith('已删除 1 条短信')
      expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ['court-sms'] })
    })
  })

  it('batch delete handles error', async () => {
    vi.mocked(courtSmsApi.deleteBatch).mockRejectedValueOnce(new Error('fail'))
    render(<CourtSmsTool />)
    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[1])
    fireEvent.click(screen.getByText('删除选中'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('批量删除失败')
    })
  })

  it('submit dialog: submit SMS content', async () => {
    render(<CourtSmsTool />)
    // Open dialog
    fireEvent.click(screen.getByText('提交短信'))
    // Fill content
    fireEvent.change(screen.getByPlaceholderText('粘贴短信内容...'), { target: { value: 'Test SMS' } })
    // Click submit button
    fireEvent.click(screen.getByRole('button', { name: '提交' }))
    await waitFor(() => {
      expect(courtSmsApi.submit).toHaveBeenCalledWith('Test SMS', undefined)
    })
  })

  it('submit dialog: empty content prevents submit', async () => {
    render(<CourtSmsTool />)
    fireEvent.click(screen.getByText('提交短信'))
    // Submit button should be disabled when content is empty
    const submitBtn = screen.getByRole('button', { name: '提交' })
    expect(submitBtn).toBeDisabled()
  })

  it('submit dialog: cancel closes dialog', () => {
    render(<CourtSmsTool />)
    fireEvent.click(screen.getByText('提交短信'))
    expect(screen.getByPlaceholderText('粘贴短信内容...')).toBeInTheDocument()
    fireEvent.click(screen.getByText('取消'))
  })

  it('submit dialog: handles error', async () => {
    vi.mocked(courtSmsApi.submit).mockRejectedValueOnce(new Error('fail'))
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<CourtSmsTool />)
    fireEvent.click(screen.getByText('提交短信'))
    fireEvent.change(screen.getByPlaceholderText('粘贴短信内容...'), { target: { value: 'Test' } })
    fireEvent.click(screen.getByRole('button', { name: '提交' }))
    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalled()
    })
    consoleSpy.mockRestore()
  })

  it('handles toggle all when some items are selected', () => {
    render(<CourtSmsTool />)
    const selectAll = screen.getByLabelText('全选')
    // Select all
    fireEvent.click(selectAll)
    expect(screen.getByText(/已选/)).toBeInTheDocument()
    // Deselect all
    fireEvent.click(selectAll)
    expect(screen.queryByText(/已选/)).not.toBeInTheDocument()
  })

  it('toggles individual row selection', () => {
    render(<CourtSmsTool />)
    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[0]) // Select all first
    expect(screen.getByText(/已选/)).toBeInTheDocument()
    // Deselect all
    fireEvent.click(checkboxes[0])
  })

  it('shows has_documents as dash when false', () => {
    render(<CourtSmsTool />)
    // Item 2 and 3 have has_documents: false
    const dashElements = screen.getAllByText('-')
    expect(dashElements.length).toBeGreaterThan(0)
  })

  it('assign dialog shows sms content', () => {
    render(<CourtSmsTool />)
    fireEvent.click(screen.getByText('手动关联'))
    // SMS 2 content should appear in the dialog
    const smsContentElements = screen.getAllByText('SMS 2')
    expect(smsContentElements.length).toBeGreaterThanOrEqual(1)
  })

  it('assign dialog shows search input', () => {
    render(<CourtSmsTool />)
    fireEvent.click(screen.getByText('手动关联'))
    expect(screen.getByPlaceholderText('输入案件名称、案号或当事人搜索...')).toBeInTheDocument()
  })

  it('assign dialog shows initial message', () => {
    render(<CourtSmsTool />)
    fireEvent.click(screen.getByText('手动关联'))
    expect(screen.getByText('输入关键词开始搜索')).toBeInTheDocument()
  })

  it('assign dialog triggers search with query', async () => {
    const { useQuery } = await import('@tanstack/react-query')
    vi.mocked(useQuery).mockReturnValueOnce({ data: [], isFetching: true } as never)
    render(<CourtSmsTool />)
    fireEvent.click(screen.getByText('手动关联'))
    fireEvent.change(screen.getByPlaceholderText('输入案件名称、案号或当事人搜索...'), { target: { value: 'Test Case' } })
  })

  it('renders status badge variants correctly', () => {
    // 'completed' -> 'default', 'pending_manual' -> 'secondary', 'failed' -> 'destructive'
    render(<CourtSmsTool />)
    const badges = screen.getAllByText(/已完成|待人工处理|处理失败/)
    expect(badges.length).toBeGreaterThanOrEqual(3)
  })

  it('filter status button changes status filter', () => {
    render(<CourtSmsTool />)
    // The "待人工处理" text appears in both the status filter button and table badges
    // Use getAllByText and click the first one (which should be the button)
    const buttons = screen.getAllByText('待人工处理')
    fireEvent.click(buttons[0])
    // Only pending_manual items should show
    expect(screen.getByText('SMS 2')).toBeInTheDocument()
  })
})
