import { render, screen } from '@testing-library/react'
import { TaskQueuePage } from '../components/TaskQueuePage'

vi.mock('lucide-react', () => ({
  RefreshCw: (props: Record<string, unknown>) => <svg data-testid="refresh-icon" {...props} />,
  Trash2: (props: Record<string, unknown>) => <svg data-testid="trash-icon" {...props} />,
}))

vi.mock('../api', () => ({
  taskQueueApi: {
    deleteTask: vi.fn(),
    deleteSchedule: vi.fn(),
    resubmitTask: vi.fn(),
  },
}))

vi.mock('../hooks/use-tasks', () => ({
  useQueuedTasks: () => ({ data: [] }),
  useCompletedTasks: () => ({ data: [] }),
  useFailedTasks: () => ({ data: [] }),
  useScheduledTasks: () => ({ data: [] }),
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: Record<string, unknown>) => <span {...props}>{children}</span>,
}))

vi.mock('@/components/ui/tabs', () => ({
  Tabs: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsContent: ({ children, value }: { children: React.ReactNode; value: string }) => <div data-tab={value}>{children}</div>,
  TabsList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsTrigger: ({ children, value }: { children: React.ReactNode; value: string }) => <button data-value={value}>{children}</button>,
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
  AlertDialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogAction: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
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

describe('TaskQueuePage', () => {
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
})
