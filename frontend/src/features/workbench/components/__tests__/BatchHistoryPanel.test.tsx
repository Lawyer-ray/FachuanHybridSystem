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

import { render, screen } from '@testing-library/react'
import { BatchHistoryPanel } from '../BatchHistoryPanel'
import { useQuery } from '@tanstack/react-query'

describe('BatchHistoryPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows loading spinner when loading', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: true } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('shows empty state when no jobs', () => {
    vi.mocked(useQuery).mockReturnValue({ data: { items: [] }, isLoading: false } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByText('暂无批量分析历史')).toBeInTheDocument()
  })

  it('renders batch jobs when data is available', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: {
        items: [
          { id: 'job-1', status: 'completed', total_items: 5, completed_items: 5, failed_items: 0, prompt: 'Analyze', created_at: '2025-01-01T00:00:00Z', summary_file: true, detail_zip_file: false },
        ],
      },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByText('已完成')).toBeInTheDocument()
  })

  it('renders file count for each job', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: {
        items: [
          { id: 'job-1', status: 'completed', total_items: 5, completed_items: 5, failed_items: 0, prompt: 'Test', created_at: '2025-01-01T00:00:00Z' },
        ],
      },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByText('5 个文件')).toBeInTheDocument()
  })

  it('shows CSV download button when summary_file exists', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: {
        items: [
          { id: 'job-1', status: 'completed', total_items: 5, completed_items: 5, failed_items: 0, prompt: 'Test', created_at: '2025-01-01T00:00:00Z', summary_file: true },
        ],
      },
      isLoading: false,
    } as ReturnType<typeof useQuery>)
    render(<BatchHistoryPanel sessionId={1} />)
    expect(screen.getByText('CSV')).toBeInTheDocument()
  })
})
