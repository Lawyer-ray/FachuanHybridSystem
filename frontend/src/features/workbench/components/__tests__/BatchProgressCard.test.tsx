vi.mock('../api', () => ({
  retryBatchAnalysis: vi.fn(),
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { render, screen } from '@testing-library/react'
import { BatchProgressCard } from '../BatchProgressCard'

describe('BatchProgressCard', () => {
  const baseJob = {
    id: 'job-1', status: 'running' as const, progress: 50, total_items: 10,
    completed_items: 4, failed_items: 1, speed_per_minute: 3, eta_seconds: 120,
    error_message: null,
  }

  const baseItems = [
    { id: 'i1', file_name: 'doc1.pdf', status: 'completed' as const, duration_ms: 2000 },
    { id: 'i2', file_name: 'doc2.pdf', status: 'running' as const },
    { id: 'i3', file_name: 'doc3.pdf', status: 'failed' as const, duration_ms: 1000 },
  ]

  it('renders title', () => {
    render(<BatchProgressCard job={baseJob as any} items={baseItems as any} onCancel={vi.fn()} />)
    expect(screen.getByText('批量文档分析')).toBeInTheDocument()
  })

  it('shows running status badge', () => {
    render(<BatchProgressCard job={baseJob as any} items={baseItems as any} onCancel={vi.fn()} />)
    expect(screen.getByText('分析中')).toBeInTheDocument()
  })

  it('shows completed status badge', () => {
    const job = { ...baseJob, status: 'completed' as const, progress: 100, eta_seconds: null }
    render(<BatchProgressCard job={job as any} items={baseItems as any} onCancel={vi.fn()} />)
    expect(screen.getByText('已完成')).toBeInTheDocument()
  })

  it('shows progress percentage', () => {
    render(<BatchProgressCard job={baseJob as any} items={baseItems as any} onCancel={vi.fn()} />)
    expect(screen.getByText('50%')).toBeInTheDocument()
  })

  it('shows stats counts', () => {
    render(<BatchProgressCard job={baseJob as any} items={baseItems as any} onCancel={vi.fn()} />)
    expect(screen.getByText(/成功: 4/)).toBeInTheDocument()
    expect(screen.getByText(/失败: 1/)).toBeInTheDocument()
  })

  it('shows cancel button when running', () => {
    render(<BatchProgressCard job={baseJob as any} items={baseItems as any} onCancel={vi.fn()} />)
    expect(screen.getByText('取消')).toBeInTheDocument()
  })
})
