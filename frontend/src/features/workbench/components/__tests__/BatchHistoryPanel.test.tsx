vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return { ...actual, useQuery: vi.fn().mockReturnValue({ data: null, isLoading: false }) }
})

vi.mock('../../api', () => ({
  listBatchJobs: vi.fn().mockResolvedValue({ items: [] }),
}))

vi.mock('@/lib/api', () => ({
  API_BASE_URL: 'http://localhost:8000',
}))

vi.mock('@/lib/token', () => ({
  getAccessToken: vi.fn(() => 'token'),
}))

vi.mock('@/components/shared', () => ({
  StatusBadge: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}))

vi.mock('lucide-react', () => ({
  History: (props: Record<string, unknown>) => <svg data-testid="icon-history" {...props} />,
  Download: (props: Record<string, unknown>) => <svg data-testid="icon-download" {...props} />,
  ChevronDown: (props: Record<string, unknown>) => <svg data-testid="icon-chevron-down" {...props} />,
  ChevronUp: (props: Record<string, unknown>) => <svg data-testid="icon-chevron-up" {...props} />,
  Loader2: (props: Record<string, unknown>) => <svg data-testid="icon-loader" {...props} />,
  CheckCircle2: (props: Record<string, unknown>) => <svg data-testid="icon-check" {...props} />,
  XCircle: (props: Record<string, unknown>) => <svg data-testid="icon-x-circle" {...props} />,
  Clock: (props: Record<string, unknown>) => <svg data-testid="icon-clock" {...props} />,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size, ...props }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} data-variant={variant} {...props}>{children}</button>
  ),
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open, onOpenChange }: { children: React.ReactNode; open: boolean; onOpenChange?: (open: boolean) => void }) =>
    open ? <div data-testid="alert-dialog" onClick={() => onOpenChange?.(false)}>{children}</div> : null,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogCancel: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => (
    <button onClick={onClick}>{children}</button>
  ),
}))

vi.mock('@/components/ui/collapsible', () => ({
  Collapsible: ({ children, open }: { children: React.ReactNode; open?: boolean }) => <div data-open={open}>{children}</div>,
  CollapsibleContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CollapsibleTrigger: ({ children, asChild }: { children: React.ReactNode; asChild?: boolean }) => <div>{children}</div>,
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { BatchHistoryPanel } from '../BatchHistoryPanel'
import { useQuery } from '@tanstack/react-query'
import { getAccessToken } from '@/lib/token'

// Helper to create a BatchJob with sensible defaults
function makeJob(overrides: Record<string, unknown> = {}) {
  return {
    id: 'job-1',
    session_id: 1,
    job_type: 'analysis',
    status: 'completed',
    prompt: 'Analyze documents',
    llm_model: 'gpt-4',
    total_items: 10,
    completed_items: 8,
    failed_items: 2,
    progress: 100,
    summary: '',
    summary_file: null,
    detail_zip_file: null,
    error_message: '',
    created_at: '2025-06-01T10:30:00Z',
    updated_at: '2025-06-01T11:00:00Z',
    started_at: '2025-06-01T10:31:00Z',
    finished_at: '2025-06-01T11:00:00Z',
    started_processing_at: null,
    eta_seconds: null,
    speed_per_minute: 0,
    ...overrides,
  }
}

describe('BatchHistoryPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Reset useQuery to default empty state for each test
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as ReturnType<typeof useQuery>)
  })

  // ─── Loading state ────────────────────────────────────────────────────

  it('shows loading spinner when loading', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: true } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
  })

  // ─── Empty state ──────────────────────────────────────────────────────

  it('shows empty state when no jobs', () => {
    vi.mocked(useQuery).mockReturnValue({ data: { items: [] }, isLoading: false } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByText('暂无批量分析历史')).toBeInTheDocument()
  })

  it('shows empty state when data is undefined (data?.items ?? [])', () => {
    vi.mocked(useQuery).mockReturnValue({ data: undefined, isLoading: false } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByText('暂无批量分析历史')).toBeInTheDocument()
  })

  // ─── Job list rendering ───────────────────────────────────────────────

  it('renders batch jobs when data is available', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: {
        items: [makeJob()],
      },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByText('已完成')).toBeInTheDocument()
  })

  it('renders file count for each job', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ total_items: 5 })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByText('5 个文件')).toBeInTheDocument()
  })

  it('renders multiple jobs', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: {
        items: [
          makeJob({ id: 'job-1', status: 'completed' }),
          makeJob({ id: 'job-2', status: 'running' }),
        ],
      },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByText('已完成')).toBeInTheDocument()
    expect(screen.getByText('运行中')).toBeInTheDocument()
  })

  // ─── Status badge display ─────────────────────────────────────────────

  it('displays "已完成" for completed status', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ status: 'completed' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByText('已完成')).toBeInTheDocument()
  })

  it('displays "运行中" for running status', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ status: 'running' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByText('运行中')).toBeInTheDocument()
  })

  it('displays "失败" for failed status', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ status: 'failed' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByText('失败')).toBeInTheDocument()
  })

  it('displays "已取消" for cancelled status', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ status: 'cancelled' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByText('已取消')).toBeInTheDocument()
  })

  it('displays raw status text for unknown status', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ status: 'pending' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByText('pending')).toBeInTheDocument()
  })

  // ─── Status icons ─────────────────────────────────────────────────────

  it('renders Loader2 icon for running status', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ status: 'running' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByTestId('icon-loader')).toBeInTheDocument()
  })

  it('renders CheckCircle2 icon for completed status', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ status: 'completed' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByTestId('icon-check')).toBeInTheDocument()
  })

  it('renders XCircle icon for failed status', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ status: 'failed' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByTestId('icon-x-circle')).toBeInTheDocument()
  })

  it('renders XCircle icon for cancelled status', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ status: 'cancelled' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByTestId('icon-x-circle')).toBeInTheDocument()
  })

  // ─── Download buttons ─────────────────────────────────────────────────

  it('shows CSV download button when summary_file exists', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ summary_file: 'path/to/summary.csv' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByText('CSV')).toBeInTheDocument()
  })

  it('does not show CSV button when summary_file is null', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ summary_file: null })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.queryByText('CSV')).not.toBeInTheDocument()
  })

  it('shows ZIP download button when detail_zip_file exists', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ detail_zip_file: 'path/to/detail.zip' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByText('ZIP')).toBeInTheDocument()
  })

  it('does not show ZIP button when detail_zip_file is null', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ detail_zip_file: null })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.queryByText('ZIP')).not.toBeInTheDocument()
  })

  // ─── CSV download dialog ──────────────────────────────────────────────

  it('opens CSV download dialog when clicking CSV button', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ summary_file: 'file.csv' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    fireEvent.click(screen.getByText('CSV'))
    expect(screen.getByText('下载汇总 CSV')).toBeInTheDocument()
    expect(screen.getByText('仅相关案例')).toBeInTheDocument()
    expect(screen.getByText('全部案例')).toBeInTheDocument()
    expect(screen.getByText('取消')).toBeInTheDocument()
  })

  // ─── ZIP download dialog ──────────────────────────────────────────────

  it('opens ZIP download dialog when clicking ZIP button', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ detail_zip_file: 'file.zip' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    fireEvent.click(screen.getByText('ZIP'))
    expect(screen.getByText('下载分析详情 ZIP')).toBeInTheDocument()
  })

  // ─── Download actions ─────────────────────────────────────────────────

  it('opens CSV download URL in new tab for all cases', () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ id: 'job-123', summary_file: 'file.csv' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    fireEvent.click(screen.getByText('CSV'))
    fireEvent.click(screen.getByText('全部案例'))
    expect(openSpy).toHaveBeenCalledWith(
      'http://localhost:8000/workbench/batch/job-123/download?token=token',
      '_blank',
    )
    openSpy.mockRestore()
  })

  it('opens CSV download URL with relevant_only param', () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ id: 'job-123', summary_file: 'file.csv' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    fireEvent.click(screen.getByText('CSV'))
    fireEvent.click(screen.getByText('仅相关案例'))
    expect(openSpy).toHaveBeenCalledWith(
      'http://localhost:8000/workbench/batch/job-123/download?token=token&relevant_only=true',
      '_blank',
    )
    openSpy.mockRestore()
  })

  it('opens ZIP download URL for all cases', () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ id: 'job-456', detail_zip_file: 'file.zip' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    fireEvent.click(screen.getByText('ZIP'))
    fireEvent.click(screen.getByText('全部案例'))
    expect(openSpy).toHaveBeenCalledWith(
      'http://localhost:8000/workbench/batch/job-456/download-detail?token=token',
      '_blank',
    )
    openSpy.mockRestore()
  })

  it('opens ZIP download URL with relevant_only param', () => {
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ id: 'job-456', detail_zip_file: 'file.zip' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    fireEvent.click(screen.getByText('ZIP'))
    fireEvent.click(screen.getByText('仅相关案例'))
    expect(openSpy).toHaveBeenCalledWith(
      'http://localhost:8000/workbench/batch/job-456/download-detail?token=token&relevant_only=true',
      '_blank',
    )
    openSpy.mockRestore()
  })

  it('omits token param when getAccessToken returns null', () => {
    vi.mocked(getAccessToken).mockReturnValue(null as unknown as string)
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ id: 'job-789', summary_file: 'file.csv' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    fireEvent.click(screen.getByText('CSV'))
    fireEvent.click(screen.getByText('全部案例'))
    expect(openSpy).toHaveBeenCalledWith(
      'http://localhost:8000/workbench/batch/job-789/download?',
      '_blank',
    )
    openSpy.mockRestore()
  })

  // ─── Collapsible details ──────────────────────────────────────────────

  it('renders details toggle button', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob()] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByText('详情')).toBeInTheDocument()
  })

  it('shows prompt text in expanded details', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ prompt: '分析合同条款' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByText(/分析合同条款/)).toBeInTheDocument()
  })

  it('shows completed and failed item counts', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ completed_items: 8, failed_items: 2 })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByText('成功 8')).toBeInTheDocument()
    expect(screen.getByText('失败 2')).toBeInTheDocument()
  })

  it('shows error message when present', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ error_message: 'Connection timeout' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByText('Connection timeout')).toBeInTheDocument()
  })

  it('does not show error message when absent', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ error_message: '' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.queryByText('Connection timeout')).not.toBeInTheDocument()
  })

  // ─── Time display ─────────────────────────────────────────────────────

  it('shows started_at time when present', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ started_at: '2025-06-01T10:31:00Z', finished_at: null })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByTestId('icon-clock')).toBeInTheDocument()
  })

  it('shows started_at and finished_at when both present', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ started_at: '2025-06-01T10:31:00Z', finished_at: '2025-06-01T11:00:00Z' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByTestId('icon-clock')).toBeInTheDocument()
    // The arrow character appears between the two dates
    expect(screen.getByText(/→/)).toBeInTheDocument()
  })

  it('does not show clock icon when started_at is null', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ started_at: null, finished_at: null })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.queryByTestId('icon-clock')).not.toBeInTheDocument()
  })

  // ─── formatDate function ─────────────────────────────────────────────

  it('formats date string correctly', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ created_at: '2025-03-15T14:05:00Z' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    // formatDate converts to local time; created_at and started_at both produce date strings
    const dateElements = screen.getAllByText(/\d+\/\d+\s+\d{2}:\d{2}/)
    expect(dateElements.length).toBeGreaterThanOrEqual(1)
  })

  it('formats null date as "-"', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ created_at: null as unknown as string })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    // formatDate(null) returns '-', the created_at field shows '-'
    expect(screen.getByText('-')).toBeInTheDocument()
    expect(screen.getByText('已完成')).toBeInTheDocument()
  })

  // ─── Dialog close ─────────────────────────────────────────────────────

  it('closes download dialog when cancel is clicked', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ summary_file: 'file.csv' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    fireEvent.click(screen.getByText('CSV'))
    expect(screen.getByTestId('alert-dialog')).toBeInTheDocument()
    // Clicking the dialog wrapper triggers onOpenChange(false)
    fireEvent.click(screen.getByTestId('alert-dialog'))
    expect(screen.queryByTestId('alert-dialog')).not.toBeInTheDocument()
  })

  // ─── Selection dialog content ─────────────────────────────────────────

  it('shows selection text in download dialog', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { items: [makeJob({ summary_file: 'file.csv' })] },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    fireEvent.click(screen.getByText('CSV'))
    expect(screen.getByText(/选择下载范围/)).toBeInTheDocument()
  })

  // ─── Falsy sessionId disables query ───────────────────────────────────

  it('does not enable query when sessionId is 0', () => {
    render(<BatchHistoryPanel sessionId={0} />)
    // When sessionId is 0 (falsy), query should not be enabled
    expect(screen.getByText('暂无批量分析历史')).toBeInTheDocument()
  })
})
