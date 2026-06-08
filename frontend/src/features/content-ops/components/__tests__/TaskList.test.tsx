vi.mock('../../hooks/use-content-ops', () => ({
  useTaskList: vi.fn().mockReturnValue({ data: [], isLoading: false, refetch: vi.fn(), isFetching: false }),
  useDeleteTask: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('framer-motion', () => ({
  motion: { div: ({ children, ...props }: any) => <div {...props}>{children}</div> },
}))

import { render, screen } from '@testing-library/react'
import { TaskList } from '../TaskList'
import { useTaskList } from '../../hooks/use-content-ops'

describe('TaskList', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders search input', () => {
    render(<TaskList selectedTaskId={null} onSelectTask={vi.fn()} />)
    expect(screen.getByPlaceholderText('搜索任务...')).toBeInTheDocument()
  })

  it('renders filter buttons', () => {
    render(<TaskList selectedTaskId={null} onSelectTask={vi.fn()} />)
    expect(screen.getByText('全部')).toBeInTheDocument()
    expect(screen.getByText('进行中')).toBeInTheDocument()
    expect(screen.getByText('已完成')).toBeInTheDocument()
  })

  it('shows empty state when no tasks', () => {
    vi.mocked(useTaskList).mockReturnValue({ data: [], isLoading: false, refetch: vi.fn(), isFetching: false } as any)
    render(<TaskList selectedTaskId={null} onSelectTask={vi.fn()} />)
    expect(screen.getByText('暂无任务记录')).toBeInTheDocument()
  })

  it('shows loading spinner when loading', () => {
    vi.mocked(useTaskList).mockReturnValue({ data: undefined, isLoading: true, refetch: vi.fn(), isFetching: false } as any)
    const { container } = render(<TaskList selectedTaskId={null} onSelectTask={vi.fn()} />)
    expect(container.querySelector('[class*="animate-spin"]')).toBeInTheDocument()
  })
})
