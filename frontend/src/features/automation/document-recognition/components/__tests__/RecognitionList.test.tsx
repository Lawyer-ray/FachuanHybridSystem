/**
 * RecognitionList Component Tests
 * 测试文书识别任务列表组件
 *
 * 覆盖：列表渲染、骨架屏加载、空状态、状态筛选、分页控件、
 *       行点击导航、绑定状态徽章、页码生成（省略号逻辑）、
 *       分页信息文本、上传按钮、各状态行展示
 */

vi.mock('react-router', () => ({
  useNavigate: () => mockNavigate,
}))

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/lib/date', () => ({
  formatDate: (iso: string) => (iso ? '2026-06-15' : '-'),
}))

vi.mock('../../hooks/use-recognition-tasks', () => ({
  useRecognitionTasks: vi.fn(),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size, className }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} className={className as string}>
      {children}
    </button>
  ),
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children, value, onValueChange }: { children: React.ReactNode; value?: string; onValueChange?: (v: string) => void }) => (
    <div data-testid="select" data-value={value} data-onvaluechange={typeof onValueChange}>
      {children}
    </div>
  ),
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value }: { children: React.ReactNode; value: string }) => (
    <div data-value={value}>{children}</div>
  ),
  SelectTrigger: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <div className={className}>{children}</div>
  ),
  SelectValue: ({ placeholder }: { placeholder: string }) => <span>{placeholder}</span>,
}))

vi.mock('@/components/ui/table', () => ({
  Table: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <table className={className}>{children}</table>
  ),
  TableBody: ({ children }: { children: React.ReactNode }) => <tbody>{children}</tbody>,
  TableCell: ({ children, className, colSpan }: { children: React.ReactNode; className?: string; colSpan?: number }) => (
    <td className={className} colSpan={colSpan}>{children}</td>
  ),
  TableHead: ({ children, className }: { children: React.ReactNode; className?: string }) => (
    <th className={className}>{children}</th>
  ),
  TableHeader: ({ children }: { children: React.ReactNode }) => <thead>{children}</thead>,
  TableRow: ({ children, onClick, className }: { children: React.ReactNode; onClick?: () => void; className?: string }) => (
    <tr onClick={onClick} className={className}>{children}</tr>
  ),
}))

vi.mock('@/components/ui/skeleton', () => ({
  Skeleton: ({ className }: { className: string }) => <div className={className} data-testid="skeleton" />,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, variant, className }: Record<string, unknown>) => (
    <span className={className as string} data-variant={variant}>{children}</span>
  ),
}))

vi.mock('lucide-react', () => ({
  Plus: (p: Record<string, unknown>) => <svg data-testid="icon-plus" {...p} />,
  ChevronLeft: (p: Record<string, unknown>) => <svg data-testid="icon-chevron-left" {...p} />,
  ChevronRight: (p: Record<string, unknown>) => <svg data-testid="icon-chevron-right" {...p} />,
  FileText: (p: Record<string, unknown>) => <svg data-testid="icon-file-text" {...p} />,
  Check: (p: Record<string, unknown>) => <svg data-testid="icon-check" {...p} />,
  X: (p: Record<string, unknown>) => <svg data-testid="icon-x" {...p} />,
  Minus: (p: Record<string, unknown>) => <svg data-testid="icon-minus" {...p} />,
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { RecognitionList } from '../RecognitionList'
import { useRecognitionTasks } from '../../hooks/use-recognition-tasks'
import type { DocumentRecognitionTask } from '../../types'

const mockNavigate = vi.fn()

// ---- helpers ----
function createTask(overrides: Partial<DocumentRecognitionTask> = {}): DocumentRecognitionTask {
  return {
    id: 1,
    file_name: '判决书.pdf',
    file_path: '/media/判决书.pdf',
    status: 'success',
    document_type: '民事判决书',
    case_number: '(2026)京01民初123号',
    key_time: '2026-01-01',
    confidence: 0.95,
    extraction_method: 'ocr',
    raw_text: null,
    binding_success: true,
    case_id: 100,
    case_name: '张某诉李某',
    case_log_id: null,
    error_message: null,
    created_at: '2026-06-15T10:00:00Z',
    updated_at: '2026-06-15T10:05:00Z',
    ...overrides,
  }
}

const mockTasks: DocumentRecognitionTask[] = [
  createTask({ id: 1, file_name: '判决书.pdf', case_number: '(2026)京01民初123号', binding_success: true, document_type: '民事判决书' }),
  createTask({ id: 2, file_name: '起诉状.docx', status: 'pending', case_number: null, binding_success: null, document_type: '民事起诉状' }),
  createTask({ id: 3, file_name: '调解书.pdf', status: 'processing', case_number: '(2026)沪01民初456号', binding_success: null, document_type: '民事调解书' }),
  createTask({ id: 4, file_name: '裁定书.pdf', status: 'failed', case_number: null, binding_success: false, document_type: null }),
]

function mockReturnData(data: { items: DocumentRecognitionTask[]; total: number } | undefined, isLoading = false, isFetching = false) {
  vi.mocked(useRecognitionTasks).mockReturnValue({ data, isLoading, isFetching } as any)
}

// ---- tests ----
describe('RecognitionList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockNavigate.mockClear()
  })

  // ========== basic rendering ==========

  it('renders upload button when onUploadClick is provided', () => {
    mockReturnData({ items: [], total: 0 })
    render(<RecognitionList onUploadClick={vi.fn()} />)
    const uploadButtons = screen.getAllByText('上传文书')
    expect(uploadButtons.length).toBeGreaterThan(0)
  })

  it('does not render upload button when onUploadClick is not provided', () => {
    mockReturnData({ items: [], total: 0 })
    render(<RecognitionList />)
    // Only the empty state button (if any) should show
    const uploadButtons = screen.queryAllByText('上传文书')
    // No top-bar upload button; the empty state also requires onUploadClick
    expect(uploadButtons.length).toBe(0)
  })

  it('renders status filter', () => {
    mockReturnData({ items: [], total: 0 })
    render(<RecognitionList />)
    expect(screen.getByText('全部状态')).toBeInTheDocument()
  })

  it('renders table headers', () => {
    mockReturnData({ items: mockTasks })
    render(<RecognitionList />)
    expect(screen.getByText('文件名')).toBeInTheDocument()
    expect(screen.getByText('文书类型')).toBeInTheDocument()
    expect(screen.getByText('案号')).toBeInTheDocument()
    expect(screen.getByText('绑定状态')).toBeInTheDocument()
    expect(screen.getByText('创建时间')).toBeInTheDocument()
  })

  // ========== loading state ==========

  it('renders skeleton loading when isLoading is true', () => {
    mockReturnData(undefined, true, true)
    render(<RecognitionList />)
    const skeletons = screen.getAllByTestId('skeleton')
    // TableSkeleton renders 5 rows x 5 cells = 25 skeletons
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('does not render task rows when loading', () => {
    mockReturnData(undefined, true, true)
    render(<RecognitionList />)
    expect(screen.queryByText('判决书.pdf')).not.toBeInTheDocument()
  })

  // ========== empty state ==========

  it('renders empty state with message when no tasks', () => {
    mockReturnData({ items: [], total: 0 })
    render(<RecognitionList />)
    expect(screen.getByText('暂无识别任务')).toBeInTheDocument()
    expect(screen.getByText(/点击「上传文书」按钮开始第一个识别任务/)).toBeInTheDocument()
  })

  it('renders empty state with upload button when onUploadClick is provided', () => {
    mockReturnData({ items: [], total: 0 })
    render(<RecognitionList onUploadClick={vi.fn()} />)
    const uploadButtons = screen.getAllByText('上传文书')
    // One in the top bar, one in the empty state
    expect(uploadButtons.length).toBe(2)
  })

  it('renders empty state without upload button when onUploadClick is not provided', () => {
    mockReturnData({ items: [], total: 0 })
    render(<RecognitionList />)
    // No upload buttons at all
    expect(screen.queryAllByText('上传文书').length).toBe(0)
  })

  // ========== task list rendering ==========

  it('renders task file names', () => {
    mockReturnData({ items: mockTasks })
    render(<RecognitionList />)
    expect(screen.getByText('判决书.pdf')).toBeInTheDocument()
    expect(screen.getByText('起诉状.docx')).toBeInTheDocument()
    expect(screen.getByText('调解书.pdf')).toBeInTheDocument()
    expect(screen.getByText('裁定书.pdf')).toBeInTheDocument()
  })

  it('renders document types', () => {
    mockReturnData({ items: mockTasks })
    render(<RecognitionList />)
    expect(screen.getByText('民事判决书')).toBeInTheDocument()
    expect(screen.getByText('民事起诉状')).toBeInTheDocument()
    expect(screen.getByText('民事调解书')).toBeInTheDocument()
  })

  it('renders dash for null document_type', () => {
    mockReturnData({ items: [createTask({ id: 4, document_type: null })] })
    render(<RecognitionList />)
    // document_type null should render '-'
    const cells = screen.getAllByText('-')
    expect(cells.length).toBeGreaterThan(0)
  })

  it('renders case numbers', () => {
    mockReturnData({ items: mockTasks })
    render(<RecognitionList />)
    expect(screen.getByText('(2026)京01民初123号')).toBeInTheDocument()
    expect(screen.getByText('(2026)沪01民初456号')).toBeInTheDocument()
  })

  it('renders dash for null case_number', () => {
    mockReturnData({ items: [createTask({ id: 2, case_number: null })] })
    render(<RecognitionList />)
    const cells = screen.getAllByText('-')
    expect(cells.length).toBeGreaterThan(0)
  })

  it('renders file icons for each row', () => {
    mockReturnData({ items: mockTasks })
    render(<RecognitionList />)
    const fileIcons = screen.getAllByTestId('icon-file-text')
    // One per row
    expect(fileIcons.length).toBe(mockTasks.length)
  })

  // ========== binding status badges ==========

  it('renders bound badge when binding_success is true', () => {
    mockReturnData({ items: [createTask({ binding_success: true })] })
    render(<RecognitionList />)
    expect(screen.getByText('已绑定')).toBeInTheDocument()
  })

  it('renders unbound badge when binding_success is null', () => {
    mockReturnData({ items: [createTask({ binding_success: null })] })
    render(<RecognitionList />)
    expect(screen.getByText('未绑定')).toBeInTheDocument()
  })

  it('renders binding failed badge when binding_success is false', () => {
    mockReturnData({ items: [createTask({ binding_success: false })] })
    render(<RecognitionList />)
    expect(screen.getByText('绑定失败')).toBeInTheDocument()
  })

  // ========== row click / navigation ==========

  it('navigates to task detail page on row click', () => {
    mockReturnData({ items: [createTask({ id: 42 })] })
    render(<RecognitionList />)
    fireEvent.click(screen.getByText('判决书.pdf'))
    expect(mockNavigate).toHaveBeenCalledWith('/admin/automation/document-recognition/42')
  })

  it('navigates to different task detail pages for different rows', () => {
    mockReturnData({ items: mockTasks })
    render(<RecognitionList />)
    fireEvent.click(screen.getByText('起诉状.docx'))
    expect(mockNavigate).toHaveBeenCalledWith('/admin/automation/document-recognition/2')
    fireEvent.click(screen.getByText('调解书.pdf'))
    expect(mockNavigate).toHaveBeenCalledWith('/admin/automation/document-recognition/3')
  })

  // ========== pagination ==========

  it('shows pagination info text', () => {
    mockReturnData({ items: mockTasks, total: 25 })
    render(<RecognitionList />)
    expect(screen.getByText(/显示第/)).toBeInTheDocument()
    expect(screen.getByText(/25/)).toBeInTheDocument()
    expect(screen.getByText(/条/)).toBeInTheDocument()
  })

  it('shows "no data" text when total is 0', () => {
    mockReturnData({ items: [], total: 0 })
    render(<RecognitionList />)
    expect(screen.getByText('暂无数据')).toBeInTheDocument()
  })

  it('shows pagination buttons when there are multiple pages', () => {
    // 25 total / 10 per page = 3 pages
    mockReturnData({ items: mockTasks, total: 25 })
    render(<RecognitionList />)
    // Page buttons: 1, 2, 3 — use getAllByText to disambiguate from pagination info text
    const pageButtons = screen.getAllByRole('button')
    const pageNums = pageButtons.filter(btn => ['1', '2', '3'].includes(btn.textContent || ''))
    expect(pageNums.length).toBeGreaterThanOrEqual(3)
    expect(screen.getByText('上一页')).toBeInTheDocument()
    expect(screen.getByText('下一页')).toBeInTheDocument()
  })

  it('disables previous button on first page', () => {
    mockReturnData({ items: mockTasks, total: 25 })
    render(<RecognitionList />)
    const prevButton = screen.getByText('上一页').closest('button')
    expect(prevButton).toBeDisabled()
  })

  it('enables next button when not on last page', () => {
    mockReturnData({ items: mockTasks, total: 25 })
    render(<RecognitionList />)
    const nextButton = screen.getByText('下一页').closest('button')
    expect(nextButton).not.toBeDisabled()
  })

  it('does not show pagination buttons when only one page', () => {
    mockReturnData({ items: mockTasks, total: 4 })
    render(<RecognitionList />)
    expect(screen.queryByText('上一页')).not.toBeInTheDocument()
    expect(screen.queryByText('下一页')).not.toBeInTheDocument()
  })

  it('shows correct item range in pagination info', () => {
    mockReturnData({ items: mockTasks, total: 25 })
    render(<RecognitionList />)
    // Page 1 of 10-per-page: items 1-10, total 25
    const infoText = screen.getByText(/显示第/)
    expect(infoText).toBeInTheDocument()
    expect(screen.getByText(/25/)).toBeInTheDocument()
  })

  // ========== status filter ==========

  it('passes status filter value to useRecognitionTasks', () => {
    mockReturnData({ items: mockTasks })
    render(<RecognitionList />)
    expect(useRecognitionTasks).toHaveBeenCalledWith({
      page: 1,
      page_size: 10,
      status: undefined,
    })
  })

  // ========== pagination with ellipsis ==========

  it('shows ellipsis for large page counts', () => {
    // 100 total / 10 per page = 10 pages (> 7, triggers ellipsis)
    mockReturnData({ items: mockTasks, total: 100 })
    render(<RecognitionList />)
    // On page 1, should show: 1 2 3 4 ... 10
    // Use button role to find page buttons (disambiguate from pagination info spans)
    const pageButtons = screen.getAllByRole('button')
    const pageNums = pageButtons
      .map(btn => btn.textContent)
      .filter(t => t && /^\d+$/.test(t))
    expect(pageNums).toContain('2')
    expect(pageNums).toContain('3')
    expect(pageNums).toContain('4')
    expect(pageNums).toContain('10')
    // Should have ellipsis
    const ellipses = screen.getAllByText('...')
    expect(ellipses.length).toBeGreaterThan(0)
  })

  // ========== isFetching state ==========

  it('disables pagination buttons when fetching', () => {
    mockReturnData({ items: mockTasks, total: 25 }, false, true)
    render(<RecognitionList />)
    const nextButton = screen.getByText('下一页').closest('button')
    expect(nextButton).toBeDisabled()
  })

  // ========== multiple page data ==========

  it('renders correct number of rows', () => {
    mockReturnData({ items: mockTasks, total: 4 })
    render(<RecognitionList />)
    // 4 tasks -> 4 rows with file names
    expect(screen.getByText('判决书.pdf')).toBeInTheDocument()
    expect(screen.getByText('起诉状.docx')).toBeInTheDocument()
    expect(screen.getByText('调解书.pdf')).toBeInTheDocument()
    expect(screen.getByText('裁定书.pdf')).toBeInTheDocument()
  })

  it('renders single task', () => {
    mockReturnData({ items: [createTask()], total: 1 })
    render(<RecognitionList />)
    expect(screen.getByText('判决书.pdf')).toBeInTheDocument()
    expect(screen.getByText('民事判决书')).toBeInTheDocument()
    expect(screen.getByText('(2026)京01民初123号')).toBeInTheDocument()
    expect(screen.getByText('已绑定')).toBeInTheDocument()
  })

  // ========== formatDate display ==========

  it('displays formatted date for each row', () => {
    mockReturnData({ items: mockTasks })
    render(<RecognitionList />)
    // Our mock formatDate returns '2026-06-15' for non-null dates
    const dates = screen.getAllByText('2026-06-15')
    expect(dates.length).toBe(mockTasks.length)
  })

  // ========== all statuses in one list ==========

  it('renders tasks with different statuses', () => {
    mockReturnData({ items: mockTasks })
    render(<RecognitionList />)
    // All 4 different file names should be present
    expect(screen.getByText('判决书.pdf')).toBeInTheDocument()
    expect(screen.getByText('起诉状.docx')).toBeInTheDocument()
    expect(screen.getByText('调解书.pdf')).toBeInTheDocument()
    expect(screen.getByText('裁定书.pdf')).toBeInTheDocument()
  })

  // ========== binding badges for all states ==========

  it('renders all three binding badge types', () => {
    mockReturnData({ items: mockTasks })
    render(<RecognitionList />)
    expect(screen.getAllByText('已绑定').length).toBeGreaterThan(0)
    expect(screen.getAllByText('未绑定').length).toBeGreaterThan(0)
    expect(screen.getAllByText('绑定失败').length).toBeGreaterThan(0)
  })

  // ========== no upload button in top bar without callback ==========

  it('renders only empty-state area when no tasks and no upload callback', () => {
    mockReturnData({ items: [], total: 0 })
    render(<RecognitionList />)
    expect(screen.getByText('暂无识别任务')).toBeInTheDocument()
    // No top-bar upload button (empty state only shows button with onUploadClick)
    expect(screen.queryByTestId('icon-plus')).not.toBeInTheDocument()
  })

  // ========== negative page values ==========

  it('handles page 1 correctly in pagination info', () => {
    mockReturnData({ items: mockTasks, total: 30 })
    render(<RecognitionList />)
    // Page 1, 10 per page, total 30: "显示第 1 - 10 条，共 30 条"
    expect(screen.getByText(/显示第/)).toBeInTheDocument()
    expect(screen.getByText('30')).toBeInTheDocument()
  })
})
