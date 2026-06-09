import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { TaskQueuePage } from '../components/TaskQueuePage'
import { taskQueueApi } from '../api'

vi.mock('lucide-react', () => ({
  RefreshCw: (props: Record<string, unknown>) => <svg data-testid="refresh-icon" {...props} />,
  Trash2: (props: Record<string, unknown>) => <svg data-testid="trash-icon" {...props} />,
}))

vi.mock('../api', () => ({
  taskQueueApi: {
    deleteTask: vi.fn().mockResolvedValue({}),
    deleteSchedule: vi.fn().mockResolvedValue({}),
    resubmitTask: vi.fn().mockResolvedValue({}),
  },
}))

let hookOverrides: Record<string, unknown> = {}

vi.mock('../hooks/use-tasks', () => ({
  useQueuedTasks: () => hookOverrides.queued ?? { data: [] },
  useCompletedTasks: () => hookOverrides.completed ?? { data: [] },
  useFailedTasks: () => hookOverrides.failed ?? { data: [] },
  useScheduledTasks: () => hookOverrides.scheduled ?? { data: [] },
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size, className }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} className={className as string}>{children}</button>
  ),
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, variant }: Record<string, unknown>) => <span data-variant={variant}>{children}</span>,
}))

vi.mock('@/components/ui/tabs', () => ({
  Tabs: ({ children, value, onValueChange }: { children: React.ReactNode; value?: string; onValueChange?: (v: string) => void }) => <div data-value={value}>{children}</div>,
  TabsContent: ({ children, value }: { children: React.ReactNode; value: string }) => <div data-tab={value}>{children}</div>,
  TabsList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsTrigger: ({ children, value, onClick }: { children: React.ReactNode; value: string; onClick?: () => void }) => <button data-value={value} onClick={onClick}>{children}</button>,
}))

vi.mock('@/components/ui/table', () => ({
  Table: ({ children }: { children: React.ReactNode }) => <table>{children}</table>,
  TableBody: ({ children }: { children: React.ReactNode }) => <tbody>{children}</tbody>,
  TableCell: ({ children }: { children: React.ReactNode }) => <td>{children}</td>,
  TableHead: ({ children }: { children: React.ReactNode }) => <th>{children}</th>,
  TableHeader: ({ children }: { children: React.ReactNode }) => <thead>{children}</thead>,
  TableRow: ({ children }: { children: React.ReactNode }) => <tr>{children}</tr>,
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) => open ? <div data-testid="alert-dialog">{children}</div> : null,
  AlertDialogAction: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => <button onClick={onClick}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/shared/EmptyState', () => ({
  EmptyState: ({ title, description }: { title: string; description: string }) => (
    <div data-testid="empty-state">
      <span>{title}</span>
      <span>{description}</span>
    </div>
  ),
}))

const queuedTasks = [
  { id: 'task-1', name: '任务A', group: 'default', func: 'myapp.tasks.process_task_a', created_at: '2024-01-01 10:00' },
  { id: 'task-2', name: '任务B', group: null, func: 'myapp.tasks.process_task_b_long_name_very_long', created_at: '2024-01-01 11:00' },
]

const completedTasks = [
  { id: 'task-3', name: '任务C', group: 'default', func: 'myapp.tasks.done', started_at: '2024-01-01 09:00', duration: 45.2, result: null },
  { id: 'task-4', name: null, group: null, func: 'myapp.tasks.done2', started_at: '2024-01-01 08:00', duration: 0.5, result: null },
]

const failedTasks = [
  { id: 'task-5', name: '任务D', group: 'default', func: 'myapp.tasks.fail', started_at: '2024-01-01 07:00', result: 'Error: something went wrong with the task execution' },
]

const scheduledTasks = [
  { id: 1, name: '定时任务A', func: 'myapp.tasks.scheduled', schedule_type: 'cron', repeats: -1, next_run: '2024-01-02 10:00', last_run: '2024-01-01 10:00' },
  { id: 2, name: null, func: 'myapp.tasks.scheduled2', schedule_type: 'daily', repeats: 5, next_run: null, last_run: null },
]

describe('TaskQueuePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    hookOverrides = {}
  })

  it('renders page title', () => {
    render(<TaskQueuePage />)
    expect(screen.getByText('Task 队列')).toBeInTheDocument()
  })

  it('renders description', () => {
    render(<TaskQueuePage />)
    expect(screen.getByText(/查看 django_q 异步任务/)).toBeInTheDocument()
  })

  it('renders refresh button', () => {
    render(<TaskQueuePage />)
    expect(screen.getByText('刷新')).toBeInTheDocument()
  })

  it('shows empty state for queue tab', () => {
    render(<TaskQueuePage />)
    expect(screen.getByText('队列为空')).toBeInTheDocument()
  })

  it('shows empty state for completed tab', () => {
    render(<TaskQueuePage />)
    expect(screen.getByText('没有成功的任务')).toBeInTheDocument()
  })

  it('shows empty state for failed tab', () => {
    render(<TaskQueuePage />)
    expect(screen.getByText('没有失败的任务')).toBeInTheDocument()
  })

  it('shows empty state for scheduled tab', () => {
    render(<TaskQueuePage />)
    expect(screen.getByText('没有定时任务')).toBeInTheDocument()
  })

  it('renders queued tasks in table', () => {
    hookOverrides = { queued: { data: queuedTasks } }
    render(<TaskQueuePage />)
    expect(screen.getByText('任务A')).toBeInTheDocument()
    expect(screen.getByText('任务B')).toBeInTheDocument()
  })

  it('renders task group badge', () => {
    hookOverrides = { queued: { data: queuedTasks } }
    render(<TaskQueuePage />)
    expect(screen.getByText('default')).toBeInTheDocument()
  })

  it('renders task func name truncated', () => {
    hookOverrides = { queued: { data: queuedTasks } }
    render(<TaskQueuePage />)
    // Long func name should be truncated
    expect(screen.getByText(/myapp\.tasks\.process_task_b/)).toBeInTheDocument()
  })

  it('renders completed tasks', () => {
    hookOverrides = { completed: { data: completedTasks } }
    render(<TaskQueuePage />)
    expect(screen.getByText('任务C')).toBeInTheDocument()
  })

  it('renders duration for completed tasks', () => {
    hookOverrides = { completed: { data: completedTasks } }
    render(<TaskQueuePage />)
    expect(screen.getByText(/45\.2s/)).toBeInTheDocument()
  })

  it('renders short duration for fast tasks', () => {
    hookOverrides = { completed: { data: completedTasks } }
    render(<TaskQueuePage />)
    // Duration 0.5 is < 1 so it shows "< 1s"
    expect(screen.getByText('< 1s')).toBeInTheDocument()
  })

  it('renders failed tasks with error', () => {
    hookOverrides = { failed: { data: failedTasks } }
    render(<TaskQueuePage />)
    expect(screen.getByText('任务D')).toBeInTheDocument()
    expect(screen.getByText(/something went wrong/)).toBeInTheDocument()
  })

  it('renders resubmit button for failed tasks', () => {
    hookOverrides = { failed: { data: failedTasks } }
    render(<TaskQueuePage />)
    expect(screen.getByText('重提交')).toBeInTheDocument()
  })

  it('renders scheduled tasks', () => {
    hookOverrides = { scheduled: { data: scheduledTasks } }
    render(<TaskQueuePage />)
    expect(screen.getByText('定时任务A')).toBeInTheDocument()
  })

  it('renders schedule type badge', () => {
    hookOverrides = { scheduled: { data: scheduledTasks } }
    render(<TaskQueuePage />)
    expect(screen.getByText('cron')).toBeInTheDocument()
    expect(screen.getByText('daily')).toBeInTheDocument()
  })

  it('renders permanent repeat indicator', () => {
    hookOverrides = { scheduled: { data: scheduledTasks } }
    render(<TaskQueuePage />)
    expect(screen.getByText('永久')).toBeInTheDocument()
  })

  it('handles checkbox selection', () => {
    hookOverrides = { queued: { data: queuedTasks } }
    render(<TaskQueuePage />)
    const checkboxes = screen.getAllByRole('checkbox')
    expect(checkboxes.length).toBeGreaterThan(0)
    fireEvent.click(checkboxes[0])
    // Should show batch delete button
    expect(screen.getByText(/删除选中/)).toBeInTheDocument()
  })

  it('handles select all toggle', () => {
    hookOverrides = { queued: { data: queuedTasks } }
    render(<TaskQueuePage />)
    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[0])
    fireEvent.click(checkboxes[0])
    // Deselect all
    expect(screen.queryByText(/删除选中/)).not.toBeInTheDocument()
  })

  it('handles delete task', async () => {
    hookOverrides = { queued: { data: queuedTasks } }
    render(<TaskQueuePage />)
    // Select a task
    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[1])
    // Click batch delete
    fireEvent.click(screen.getByText(/删除选中/))
    // Confirm dialog should appear
    await waitFor(() => {
      expect(screen.getByTestId('alert-dialog')).toBeInTheDocument()
    })
    // Click confirm
    fireEvent.click(screen.getByText('确定'))
    await waitFor(() => {
      expect(taskQueueApi.deleteTask).toHaveBeenCalled()
    })
  })

  it('handles resubmit task', async () => {
    hookOverrides = { failed: { data: failedTasks } }
    render(<TaskQueuePage />)
    fireEvent.click(screen.getByText('重提交'))
    await waitFor(() => {
      expect(screen.getByTestId('alert-dialog')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByText('确定'))
    await waitFor(() => {
      expect(taskQueueApi.resubmitTask).toHaveBeenCalledWith('task-5')
    })
  })

  it('handles delete schedule', async () => {
    hookOverrides = { scheduled: { data: scheduledTasks } }
    render(<TaskQueuePage />)
    // Find delete buttons
    const deleteButtons = screen.getAllByRole('button').filter(b => b.querySelector('[data-testid="trash-icon"]'))
    expect(deleteButtons.length).toBeGreaterThan(0)
    fireEvent.click(deleteButtons[0])
    await waitFor(() => {
      expect(screen.getByTestId('alert-dialog')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByText('确定'))
    await waitFor(() => {
      expect(taskQueueApi.deleteSchedule).toHaveBeenCalledWith(1)
    })
  })

  it('handles cancel in confirm dialog', async () => {
    hookOverrides = { queued: { data: queuedTasks } }
    render(<TaskQueuePage />)
    // Select a task and click batch delete
    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[1])
    fireEvent.click(screen.getByText(/删除选中/))
    await waitFor(() => {
      expect(screen.getByTestId('alert-dialog')).toBeInTheDocument()
    })
    fireEvent.click(screen.getByText('取消'))
    expect(taskQueueApi.deleteTask).not.toHaveBeenCalled()
  })

  it('renders null name as dash', () => {
    hookOverrides = { completed: { data: completedTasks } }
    render(<TaskQueuePage />)
    // task-4 has null name - should show '-'
    const dashes = screen.getAllByText('-')
    expect(dashes.length).toBeGreaterThan(0)
  })

  it('renders null func as dash', () => {
    hookOverrides = { queued: { data: [{ id: 'task-x', name: 'test', group: null, func: null, created_at: null }] } }
    render(<TaskQueuePage />)
    expect(screen.getByText('test')).toBeInTheDocument()
  })

  it('renders scheduled task with null next_run and last_run', () => {
    hookOverrides = { scheduled: { data: scheduledTasks } }
    render(<TaskQueuePage />)
    // task-2 has null next_run and last_run
    const dashes = screen.getAllByText('-')
    expect(dashes.length).toBeGreaterThan(0)
  })

  it('renders scheduled task with finite repeats', () => {
    hookOverrides = { scheduled: { data: scheduledTasks } }
    render(<TaskQueuePage />)
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('renders tab counts', () => {
    hookOverrides = {
      queued: { data: queuedTasks },
      completed: { data: completedTasks },
      failed: { data: failedTasks },
      scheduled: { data: scheduledTasks },
    }
    render(<TaskQueuePage />)
    expect(screen.getByText(/队列中 \(2\)/)).toBeInTheDocument()
    expect(screen.getByText(/成功 \(2\)/)).toBeInTheDocument()
    expect(screen.getByText(/失败 \(1\)/)).toBeInTheDocument()
    expect(screen.getByText(/定时 \(2\)/)).toBeInTheDocument()
  })

  it('renders checkbox select all for completed tasks', () => {
    hookOverrides = { completed: { data: completedTasks } }
    render(<TaskQueuePage />)
    const checkboxes = screen.getAllByRole('checkbox')
    expect(checkboxes.length).toBeGreaterThan(1)
  })

  it('renders checkbox select all for failed tasks', () => {
    hookOverrides = { failed: { data: failedTasks } }
    render(<TaskQueuePage />)
    const checkboxes = screen.getAllByRole('checkbox')
    expect(checkboxes.length).toBeGreaterThan(1)
  })

  it('handles batch delete with empty selection', () => {
    hookOverrides = { queued: { data: queuedTasks } }
    render(<TaskQueuePage />)
    // Without selecting anything, batch delete should not appear
    expect(screen.queryByText(/删除选中/)).not.toBeInTheDocument()
  })

  it('handles toggle select individual task', () => {
    hookOverrides = { queued: { data: queuedTasks } }
    render(<TaskQueuePage />)
    const checkboxes = screen.getAllByRole('checkbox')
    // Click individual task checkbox (skip first which is select-all)
    fireEvent.click(checkboxes[1])
    expect(screen.getByText(/删除选中/)).toBeInTheDocument()
    // Click again to deselect
    fireEvent.click(checkboxes[1])
    expect(screen.queryByText(/删除选中/)).not.toBeInTheDocument()
  })

  it('handles toggle select all then deselect all', () => {
    hookOverrides = { queued: { data: queuedTasks } }
    render(<TaskQueuePage />)
    const checkboxes = screen.getAllByRole('checkbox')
    // Select all
    fireEvent.click(checkboxes[0])
    expect(screen.getByText(/删除选中 \(2\)/)).toBeInTheDocument()
    // Deselect all
    fireEvent.click(checkboxes[0])
    expect(screen.queryByText(/删除选中/)).not.toBeInTheDocument()
  })

  it('handles duration formatting for null', () => {
    hookOverrides = { completed: { data: [{ id: 'task-x', name: 'test', group: null, func: 'func', started_at: '2024-01-01', duration: null }] } }
    render(<TaskQueuePage />)
    // '-' appears in multiple places, use getAllByText
    expect(screen.getAllByText('-').length).toBeGreaterThan(0)
  })

  it('handles duration formatting for less than 1 second', () => {
    hookOverrides = { completed: { data: [{ id: 'task-x', name: 'test', group: null, func: 'func', started_at: '2024-01-01', duration: 0.3 }] } }
    render(<TaskQueuePage />)
    expect(screen.getByText('< 1s')).toBeInTheDocument()
  })

  it('handles duration formatting for minutes', () => {
    hookOverrides = { completed: { data: [{ id: 'task-x', name: 'test', group: null, func: 'func', started_at: '2024-01-01', duration: 125.7 }] } }
    render(<TaskQueuePage />)
    expect(screen.getByText(/2m/)).toBeInTheDocument()
  })
})
