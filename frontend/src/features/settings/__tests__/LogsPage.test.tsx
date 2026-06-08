import { render, screen } from '@testing-library/react'
import { LogsPage } from '../components/LogsPage'

vi.mock('lucide-react', () => ({
  Search: (props: Record<string, unknown>) => <svg data-testid="search-icon" {...props} />,
  Loader2: (props: Record<string, unknown>) => <svg data-testid="loader-icon" {...props} />,
  Plus: (props: Record<string, unknown>) => <svg data-testid="plus-icon" {...props} />,
  Clock: (props: Record<string, unknown>) => <svg data-testid="clock-icon" {...props} />,
  Paperclip: (props: Record<string, unknown>) => <svg data-testid="paperclip" {...props} />,
  Bell: (props: Record<string, unknown>) => <svg data-testid="bell-icon" {...props} />,
  Trash2: (props: Record<string, unknown>) => <svg data-testid="trash-icon" {...props} />,
}))

vi.mock('@/lib/date', () => ({
  formatDate: (d: string) => d ?? '',
}))

vi.mock('@/features/cases/api', () => ({
  caseApi: {
    listAllLogs: vi.fn().mockResolvedValue([]),
    list: vi.fn().mockResolvedValue([]),
    createLog: vi.fn(),
    deleteLog: vi.fn(),
  },
}))

vi.mock('@/features/cases/types', () => ({
  CASE_LOG_REMINDER_TYPE_LABELS: {
    hearing: { zh: '开庭' },
    deadline: { zh: '截止日期' },
  },
}))

vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query')
  return {
    ...actual,
    useQuery: vi.fn(() => ({ data: [], isLoading: false })),
    useMutation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
    useQueryClient: vi.fn(() => ({ invalidateQueries: vi.fn() })),
    keepPreviousData: 'keepPreviousData',
  }
})

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

vi.mock('@/components/ui/label', () => ({
  Label: ({ children, ...props }: Record<string, unknown>) => <label {...props}>{children}</label>,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: Record<string, unknown>) => <span {...props}>{children}</span>,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardHeader: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => <span />,
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
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
  AlertDialogTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

describe('LogsPage', () => {
  it('renders page title', () => {
    render(<LogsPage />)
    expect(screen.getByText('日志')).toBeInTheDocument()
  })

  it('renders description text', () => {
    render(<LogsPage />)
    expect(screen.getByText(/查看所有案件的操作日志/)).toBeInTheDocument()
  })

  it('renders search input', () => {
    render(<LogsPage />)
    expect(screen.getByPlaceholderText('搜索日志内容、案件名称、操作人...')).toBeInTheDocument()
  })

  it('renders add log button', () => {
    render(<LogsPage />)
    expect(screen.getByText('添加日志')).toBeInTheDocument()
  })

  it('renders empty state when no logs', () => {
    render(<LogsPage />)
    expect(screen.getByText('暂无日志')).toBeInTheDocument()
  })

  it('shows loading spinner when loading', async () => {
    const { useQuery } = await import('@tanstack/react-query')
    vi.mocked(useQuery).mockReturnValueOnce({ data: undefined, isLoading: true } as never)
    render(<LogsPage />)
    expect(screen.getByTestId('loader-icon')).toBeInTheDocument()
  })
})
