vi.mock('../../api', () => ({
  retryBatchAnalysis: vi.fn().mockResolvedValue({ success: true, message: 'ok' }),
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('lucide-react', () => ({
  Loader2: (props: Record<string, unknown>) => <svg data-testid="loader" {...props} />,
  CheckCircle2: () => <svg data-testid="check-circle" />,
  XCircle: () => <svg data-testid="x-circle" />,
  ChevronDown: () => <svg data-testid="chevron-down" />,
  ChevronUp: () => <svg data-testid="chevron-up" />,
  X: () => <svg data-testid="x-icon" />,
  RefreshCw: (props: Record<string, unknown>) => <svg data-testid="refresh" {...props} />,
  Clock: () => <svg data-testid="clock" />,
  Gauge: () => <svg data-testid="gauge" />,
}))

vi.mock('@/components/ui/collapsible', () => ({
  Collapsible: ({ children, open }: { children: React.ReactNode; open?: boolean }) => (
    <div data-testid="collapsible" data-open={String(open)}>{children}</div>
  ),
  CollapsibleContent: ({ children }: { children: React.ReactNode }) => <div data-testid="collapsible-content">{children}</div>,
  CollapsibleTrigger: ({ children, asChild }: { children: React.ReactNode; asChild?: boolean }) => <div data-testid="collapsible-trigger">{children}</div>,
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { BatchProgressCard } from '../BatchProgressCard'
import type { BatchJob, BatchJobItem, FailedItemDetail } from '../../types'

function makeJob(overrides: Partial<BatchJob> = {}): BatchJob {
  return {
    id: 'job-1', session_id: 1, job_type: '', status: 'running', prompt: '',
    llm_model: '', total_items: 3, completed_items: 0, failed_items: 0, progress: 0,
    summary: '', summary_file: '', detail_zip_file: '', error_message: '',
    created_at: '', updated_at: '', started_at: null, finished_at: null,
    started_processing_at: null, eta_seconds: null, speed_per_minute: 0,
    ...overrides,
  }
}

function makeItem(overrides: Partial<BatchJobItem> = {}): BatchJobItem {
  return {
    id: 'item-1', file_name: 'file.pdf', status: 'pending',
    result: '', error: '', duration_ms: null, ...overrides,
  }
}

describe('BatchProgressCard', () => {
  const baseJob = makeJob()
  const baseItems: BatchJobItem[] = [
    makeItem({ id: 'i1', file_name: 'doc1.pdf', status: 'completed', duration_ms: 2000 }),
    makeItem({ id: 'i2', file_name: 'doc2.pdf', status: 'running' }),
    makeItem({ id: 'i3', file_name: 'doc3.pdf', status: 'failed', duration_ms: 1000 }),
  ]

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders title', () => {
    render(<BatchProgressCard job={baseJob} items={baseItems} onCancel={vi.fn()} />)
    expect(screen.getByText('批量文档分析')).toBeInTheDocument()
  })

  it('shows running status badge', () => {
    render(<BatchProgressCard job={baseJob} items={baseItems} onCancel={vi.fn()} />)
    expect(screen.getByText('分析中')).toBeInTheDocument()
  })

  it('shows completed status badge', () => {
    const job = makeJob({ status: 'completed', progress: 100 })
    render(<BatchProgressCard job={job} items={baseItems} onCancel={vi.fn()} />)
    expect(screen.getByText('已完成')).toBeInTheDocument()
  })

  it('shows progress percentage', () => {
    const job = makeJob({ progress: 50 })
    render(<BatchProgressCard job={job} items={baseItems} onCancel={vi.fn()} />)
    expect(screen.getByText('50%')).toBeInTheDocument()
  })

  it('shows stats counts', () => {
    const job = makeJob({ completed_items: 4, failed_items: 1 })
    render(<BatchProgressCard job={job} items={baseItems} onCancel={vi.fn()} />)
    expect(screen.getByText(/成功: 4/)).toBeInTheDocument()
    expect(screen.getByText(/失败: 1/)).toBeInTheDocument()
  })

  it('shows cancel button when running', () => {
    render(<BatchProgressCard job={baseJob} items={baseItems} onCancel={vi.fn()} />)
    expect(screen.getByText('取消')).toBeInTheDocument()
  })

  // --- Branch coverage tests ---

  it('formatDuration: renders seconds for < 60s', () => {
    const job = makeJob({ status: 'completed' })
    const items = [makeItem({ status: 'completed', duration_ms: 45000 })]
    render(<BatchProgressCard job={job} items={items} onCancel={vi.fn()} />)
    expect(screen.getByText('45.0s')).toBeInTheDocument()
  })

  it('formatDuration: renders minutes for < 3600s ETA', () => {
    const job = makeJob({ status: 'running', eta_seconds: 120 })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    expect(screen.getByText(/2分钟/)).toBeInTheDocument()
  })

  it('formatDuration: renders hours+minutes for >= 3600s ETA', () => {
    const job = makeJob({ status: 'running', eta_seconds: 3700 })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    expect(screen.getByText(/1小时2分钟/)).toBeInTheDocument()
  })

  it('renders failed status with error message', () => {
    const job = makeJob({ status: 'failed', error_message: 'Timeout error' })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    expect(screen.getByText('失败')).toBeInTheDocument()
    expect(screen.getByText('Timeout error')).toBeInTheDocument()
  })

  it('renders cancelled status', () => {
    const job = makeJob({ status: 'cancelled' })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    expect(screen.getByText('已取消')).toBeInTheDocument()
  })

  it('renders unknown status as-is', () => {
    const job = makeJob({ status: 'unknown' as BatchJob['status'] })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    expect(screen.getByText('unknown')).toBeInTheDocument()
  })

  it('shows retry button when terminal with failed items', () => {
    const job = makeJob({ status: 'completed', failed_items: 2 })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    expect(screen.getByText('重试失败项')).toBeInTheDocument()
  })

  it('calls retry API on retry click', async () => {
    const { retryBatchAnalysis } = await import('../../api')
    const job = makeJob({ status: 'completed', failed_items: 1 })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    fireEvent.click(screen.getByText('重试失败项'))
    expect(retryBatchAnalysis).toHaveBeenCalledWith('job-1')
  })

  it('shows error toast on retry failure', async () => {
    const { retryBatchAnalysis } = await import('../../api')
    const { toast } = await import('sonner')
    vi.mocked(retryBatchAnalysis).mockRejectedValueOnce(new Error('fail'))
    const job = makeJob({ status: 'completed', failed_items: 1 })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    fireEvent.click(screen.getByText('重试失败项'))
    await screen.findByText('重试失败项')
    expect(toast.error).toHaveBeenCalledWith('重试请求失败')
  })

  it('shows error toast when retry returns success=false', async () => {
    const { retryBatchAnalysis } = await import('../../api')
    const { toast } = await import('sonner')
    vi.mocked(retryBatchAnalysis).mockResolvedValueOnce({ success: false, message: 'Cannot retry' })
    const job = makeJob({ status: 'completed', failed_items: 1 })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    fireEvent.click(screen.getByText('重试失败项'))
    await screen.findByText('重试失败项')
    expect(toast.error).toHaveBeenCalledWith('Cannot retry')
  })

  it('shows success toast on retry success', async () => {
    const { toast } = await import('sonner')
    const job = makeJob({ status: 'completed', failed_items: 1 })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    fireEvent.click(screen.getByText('重试失败项'))
    await screen.findByText('重试失败项')
    expect(toast.success).toHaveBeenCalledWith('ok')
  })

  it('shows dismiss button when terminal and onDismiss provided', () => {
    const onDismiss = vi.fn()
    const job = makeJob({ status: 'completed' })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} onDismiss={onDismiss} />)
    fireEvent.click(screen.getByText('关闭'))
    expect(onDismiss).toHaveBeenCalled()
  })

  it('hides dismiss when onDismiss not provided', () => {
    const job = makeJob({ status: 'completed' })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    expect(screen.queryByText('关闭')).not.toBeInTheDocument()
  })

  it('hides retry button when terminal but no failed items', () => {
    const job = makeJob({ status: 'completed', failed_items: 0 })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    expect(screen.queryByText('重试失败项')).not.toBeInTheDocument()
  })

  it('shows speed display when running with speed > 0', () => {
    const job = makeJob({ status: 'running', speed_per_minute: 5.3 })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    expect(screen.getByText(/5\.3 文件\/分钟/)).toBeInTheDocument()
  })

  it('hides speed when speed is 0', () => {
    const job = makeJob({ status: 'running', speed_per_minute: 0 })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    expect(screen.queryByText(/文件\/分钟/)).not.toBeInTheDocument()
  })

  it('shows ETA when running and eta > 0', () => {
    const job = makeJob({ status: 'running', eta_seconds: 120 })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    expect(screen.getByText(/预计剩余/)).toBeInTheDocument()
  })

  it('hides ETA when eta_seconds is null', () => {
    const job = makeJob({ status: 'running', eta_seconds: null })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    expect(screen.queryByText(/预计剩余/)).not.toBeInTheDocument()
  })

  it('hides ETA when eta_seconds is 0', () => {
    const job = makeJob({ status: 'running', eta_seconds: 0 })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    expect(screen.queryByText(/预计剩余/)).not.toBeInTheDocument()
  })

  it('shows pending item icon', () => {
    const job = makeJob({ status: 'running' })
    const items = [makeItem({ status: 'pending' })]
    render(<BatchProgressCard job={job} items={items} onCancel={vi.fn()} />)
    expect(screen.getByText('file.pdf')).toBeInTheDocument()
  })

  it('shows failed item detail with error', () => {
    const job = makeJob({ status: 'completed' })
    const items = [makeItem({ status: 'completed', duration_ms: 1000 })]
    const failed: FailedItemDetail[] = [{ id: 'f1', file_name: 'bad.pdf', error: 'Parse error' }]
    render(<BatchProgressCard job={job} items={items} onCancel={vi.fn()} failedItemsDetail={failed} />)
    expect(screen.getByText('bad.pdf')).toBeInTheDocument()
    expect(screen.getByText(/Parse error/)).toBeInTheDocument()
  })

  it('shows failed item detail without error string', () => {
    const job = makeJob({ status: 'completed' })
    const items = [makeItem({ status: 'completed', duration_ms: 1000 })]
    const failed: FailedItemDetail[] = [{ id: 'f1', file_name: 'bad.pdf', error: '' }]
    render(<BatchProgressCard job={job} items={items} onCancel={vi.fn()} failedItemsDetail={failed} />)
    expect(screen.getByText('bad.pdf')).toBeInTheDocument()
  })

  it('hides collapsible when no items', () => {
    const job = makeJob({ status: 'running' })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    expect(screen.queryByText(/查看文件详情/)).not.toBeInTheDocument()
  })

  it('shows elapsed from duration_ms', () => {
    const job = makeJob({ status: 'completed' })
    const items = [makeItem({ status: 'completed', duration_ms: 2500 })]
    render(<BatchProgressCard job={job} items={items} onCancel={vi.fn()} />)
    expect(screen.getByText('2.5s')).toBeInTheDocument()
  })

  it('applies blue color to running item elapsed', () => {
    const job = makeJob({ status: 'running' })
    const items = [makeItem({ status: 'running', duration_ms: 1000 })]
    render(<BatchProgressCard job={job} items={items} onCancel={vi.fn()} />)
    const elapsed = screen.getByText('1.0s')
    expect(elapsed.className).toContain('text-blue-600')
  })

  it('applies muted color to completed item elapsed', () => {
    const job = makeJob({ status: 'completed' })
    const items = [makeItem({ status: 'completed', duration_ms: 1000 })]
    render(<BatchProgressCard job={job} items={items} onCancel={vi.fn()} />)
    const elapsed = screen.getByText('1.0s')
    expect(elapsed.className).toContain('text-muted-foreground')
  })

  it('shows error message section for cancelled job', () => {
    const job = makeJob({ status: 'cancelled', error_message: 'Cancelled by user' })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    expect(screen.getByText('Cancelled by user')).toBeInTheDocument()
  })

  it('hides error section when failed but no error_message', () => {
    const job = makeJob({ status: 'failed', error_message: '' })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    expect(screen.queryByText('Cancelled by user')).not.toBeInTheDocument()
  })

  it('shows loader spinner for running status', () => {
    const job = makeJob({ status: 'running' })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    expect(screen.getByTestId('loader')).toBeInTheDocument()
  })

  it('shows x-circle for failed or cancelled status', () => {
    const job = makeJob({ status: 'failed' })
    render(<BatchProgressCard job={job} items={[]} onCancel={vi.fn()} />)
    expect(screen.getByTestId('x-circle')).toBeInTheDocument()
  })

  it('renders file details in collapsible', () => {
    const job = makeJob({ status: 'completed' })
    const items = [makeItem({ status: 'completed', duration_ms: 1000 })]
    render(<BatchProgressCard job={job} items={items} onCancel={vi.fn()} />)
    expect(screen.getByText(/查看文件详情/)).toBeInTheDocument()
    expect(screen.getByText('file.pdf')).toBeInTheDocument()
  })
})
