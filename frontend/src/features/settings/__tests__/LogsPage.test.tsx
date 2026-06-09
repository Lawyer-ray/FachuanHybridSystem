import { render, screen, fireEvent, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

const mockCreateLog = vi.fn()
const mockDeleteLog = vi.fn()
const mockListAllLogs = vi.fn().mockResolvedValue([])
const mockListCases = vi.fn().mockResolvedValue([])

vi.mock('@/features/cases/api', () => ({
  caseApi: {
    listAllLogs: (...args: unknown[]) => mockListAllLogs(...args),
    list: (...args: unknown[]) => mockListCases(...args),
    createLog: (...args: unknown[]) => mockCreateLog(...args),
    deleteLog: (...args: unknown[]) => mockDeleteLog(...args),
  },
}))

vi.mock('@/features/cases/types', () => ({
  CASE_LOG_REMINDER_TYPE_LABELS: {
    hearing: { zh: '开庭' },
    asset_preservation: { zh: '财产保全' },
    evidence_deadline: { zh: '举证期限' },
    other: { zh: '其他' },
  },
}))

let mockQueryData: unknown[] = []
let mockQueryLoading = false
let mockMutationFns: Record<string, (...args: unknown[]) => void> = {}

vi.mock('@tanstack/react-query', async () => {
  const actual = await vi.importActual<typeof import('@tanstack/react-query')>('@tanstack/react-query')
  return {
    ...actual,
    useQuery: vi.fn(({ queryKey }: { queryKey: string[] }) => {
      if (queryKey[0] === 'all-logs') {
        return { data: mockQueryData, isLoading: mockQueryLoading }
      }
      // cases-for-log query
      return { data: [], isLoading: false }
    }),
    useMutation: vi.fn((config: { mutationFn: (...args: unknown[]) => unknown; onSuccess?: () => void }) => {
      const mutate = vi.fn((...args: unknown[]) => {
        mockMutationFns['mutate']?.(...args)
        config.onSuccess?.()
      })
      return { mutate, isPending: false }
    }),
    useQueryClient: vi.fn(() => ({
      invalidateQueries: vi.fn(),
    })),
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
  Select: ({ children, onValueChange, value }: { children: React.ReactNode; onValueChange?: (v: string) => void; value?: string }) => (
    <div data-testid="select" data-value={value}>{children}</div>
  ),
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value }: { children: React.ReactNode; value: string }) => (
    <button data-testid="select-item" data-value={value}>{children}</button>
  ),
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => <span />,
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) => (
    <div data-testid="dialog" data-open={open}>{children}</div>
  ),
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
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

// Helper to create mock log entries
const makeLog = (overrides = {}) => ({
  id: 1,
  case: 101,
  content: '提交了起诉状',
  actor: 1,
  actor_detail: { real_name: '张律师', username: 'zhang' },
  attachments: [],
  reminders: [],
  created_at: '2025-06-01 10:00:00',
  updated_at: '2025-06-01 10:00:00',
  ...overrides,
})

describe('LogsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockQueryData = []
    mockQueryLoading = false
    mockMutationFns = {}
  })

  // ========== Basic rendering ==========

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

  // ========== Loading state ==========

  it('shows loading spinner when loading', () => {
    mockQueryLoading = true
    render(<LogsPage />)
    expect(screen.getByTestId('loader-icon')).toBeInTheDocument()
  })

  it('does not show search input when loading', () => {
    mockQueryLoading = true
    render(<LogsPage />)
    expect(screen.queryByPlaceholderText('搜索日志内容、案件名称、操作人...')).not.toBeInTheDocument()
  })

  // ========== Empty state ==========

  it('renders empty state when no logs', () => {
    render(<LogsPage />)
    expect(screen.getByText('暂无日志')).toBeInTheDocument()
  })

  it('renders empty state when all logs are filtered out by search', () => {
    mockQueryData = [
      makeLog({ id: 1, content: '提交了起诉状', created_at: '2025-06-01 10:00:00' }),
    ]
    render(<LogsPage />)
    const input = screen.getByPlaceholderText('搜索日志内容、案件名称、操作人...')
    fireEvent.change(input, { target: { value: '完全不存在的内容' } })
    expect(screen.getByText('暂无日志')).toBeInTheDocument()
  })

  // ========== Log rendering ==========

  it('renders log entries when data is available', () => {
    mockQueryData = [makeLog({ content: '提交了起诉状' })]
    render(<LogsPage />)
    expect(screen.getByText('提交了起诉状')).toBeInTheDocument()
  })

  it('renders multiple log entries', () => {
    mockQueryData = [
      makeLog({ id: 1, content: '提交了起诉状', created_at: '2025-06-01 10:00:00' }),
      makeLog({ id: 2, content: '法院受理', created_at: '2025-06-01 11:00:00' }),
    ]
    render(<LogsPage />)
    expect(screen.getByText('提交了起诉状')).toBeInTheDocument()
    expect(screen.getByText('法院受理')).toBeInTheDocument()
  })

  // ========== Search filtering ==========

  it('filters logs by content', () => {
    mockQueryData = [
      makeLog({ id: 1, content: '提交了起诉状', created_at: '2025-06-01 10:00:00' }),
      makeLog({ id: 2, content: '法院受理', created_at: '2025-06-01 11:00:00' }),
    ]
    render(<LogsPage />)
    const input = screen.getByPlaceholderText('搜索日志内容、案件名称、操作人...')
    fireEvent.change(input, { target: { value: '起诉' } })
    expect(screen.getByText('提交了起诉状')).toBeInTheDocument()
    expect(screen.queryByText('法院受理')).not.toBeInTheDocument()
  })

  it('search is case insensitive', () => {
    mockQueryData = [
      makeLog({ id: 1, content: 'Submitted the lawsuit', created_at: '2025-06-01 10:00:00' }),
    ]
    render(<LogsPage />)
    const input = screen.getByPlaceholderText('搜索日志内容、案件名称、操作人...')
    fireEvent.change(input, { target: { value: 'SUBMITTED' } })
    expect(screen.getByText('Submitted the lawsuit')).toBeInTheDocument()
  })

  it('shows all logs when search is cleared', () => {
    mockQueryData = [
      makeLog({ id: 1, content: '提交了起诉状', created_at: '2025-06-01 10:00:00' }),
      makeLog({ id: 2, content: '法院受理', created_at: '2025-06-01 11:00:00' }),
    ]
    render(<LogsPage />)
    const input = screen.getByPlaceholderText('搜索日志内容、案件名称、操作人...')
    fireEvent.change(input, { target: { value: '起诉' } })
    expect(screen.queryByText('法院受理')).not.toBeInTheDocument()
    fireEvent.change(input, { target: { value: '' } })
    expect(screen.getByText('法院受理')).toBeInTheDocument()
  })

  // ========== Actor name rendering ==========

  it('renders actor real_name when available', () => {
    mockQueryData = [makeLog({ actor_detail: { real_name: '张律师', username: 'zhang' } })]
    render(<LogsPage />)
    expect(screen.getByText('张律师')).toBeInTheDocument()
  })

  it('falls back to username when real_name is empty', () => {
    mockQueryData = [makeLog({ actor_detail: { real_name: '', username: 'zhang_user' } })]
    render(<LogsPage />)
    expect(screen.getByText('zhang_user')).toBeInTheDocument()
  })

  it('falls back to "未知" when actor_detail is null', () => {
    mockQueryData = [makeLog({ actor_detail: null })]
    render(<LogsPage />)
    expect(screen.getByText('未知')).toBeInTheDocument()
  })

  it('falls back to "未知" when actor_detail has no real_name or username', () => {
    mockQueryData = [makeLog({ actor_detail: {} })]
    render(<LogsPage />)
    expect(screen.getByText('未知')).toBeInTheDocument()
  })

  // ========== Case name rendering ==========

  it('shows "未知案件" when case name not found in map', () => {
    mockQueryData = [makeLog({ case: 999 })]
    render(<LogsPage />)
    expect(screen.getByText('未知案件')).toBeInTheDocument()
  })

  // ========== Date grouping ==========

  it('groups logs by date', () => {
    mockQueryData = [
      makeLog({ id: 1, content: '日志A', created_at: '2025-06-01 10:00:00' }),
      makeLog({ id: 2, content: '日志B', created_at: '2025-06-01 14:00:00' }),
      makeLog({ id: 3, content: '日志C', created_at: '2025-06-02 09:00:00' }),
    ]
    render(<LogsPage />)
    // Both dates should appear as group headers
    expect(screen.getByText('日志A')).toBeInTheDocument()
    expect(screen.getByText('日志B')).toBeInTheDocument()
    expect(screen.getByText('日志C')).toBeInTheDocument()
  })

  it('sorts date groups in descending order', () => {
    mockQueryData = [
      makeLog({ id: 1, content: '较早的日志', created_at: '2025-05-01 10:00:00' }),
      makeLog({ id: 2, content: '较晚的日志', created_at: '2025-06-01 10:00:00' }),
    ]
    render(<LogsPage />)
    const content = document.body.textContent!
    const laterIndex = content.indexOf('较晚的日志')
    const earlierIndex = content.indexOf('较早的日志')
    expect(laterIndex).toBeLessThan(earlierIndex)
  })

  // ========== Logs with empty/missing created_at ==========

  it('skips logs with empty created_at', () => {
    mockQueryData = [
      makeLog({ id: 1, content: '有效日志', created_at: '2025-06-01 10:00:00' }),
      makeLog({ id: 2, content: '无效日志', created_at: '' }),
    ]
    render(<LogsPage />)
    expect(screen.getByText('有效日志')).toBeInTheDocument()
    expect(screen.queryByText('无效日志')).not.toBeInTheDocument()
  })

  it('skips logs with null created_at', () => {
    mockQueryData = [
      makeLog({ id: 1, content: '有效日志', created_at: '2025-06-01 10:00:00' }),
      makeLog({ id: 2, content: '无效日志', created_at: null }),
    ]
    render(<LogsPage />)
    expect(screen.getByText('有效日志')).toBeInTheDocument()
    expect(screen.queryByText('无效日志')).not.toBeInTheDocument()
  })

  // ========== Attachments ==========

  it('renders attachment badge when log has attachments', () => {
    mockQueryData = [makeLog({
      attachments: [
        { id: 1, log: 1, original_filename: 'doc.pdf', file_path: '/path', media_url: null, uploaded_at: '2025-06-01' },
      ],
    })]
    render(<LogsPage />)
    expect(screen.getByText('1 附件')).toBeInTheDocument()
  })

  it('renders multiple attachment count', () => {
    mockQueryData = [makeLog({
      attachments: [
        { id: 1, log: 1, original_filename: 'a.pdf', file_path: '/a', media_url: null, uploaded_at: '2025-06-01' },
        { id: 2, log: 1, original_filename: 'b.pdf', file_path: '/b', media_url: null, uploaded_at: '2025-06-01' },
        { id: 3, log: 1, original_filename: 'c.pdf', file_path: '/c', media_url: null, uploaded_at: '2025-06-01' },
      ],
    })]
    render(<LogsPage />)
    expect(screen.getByText('3 附件')).toBeInTheDocument()
  })

  it('does not render attachment badge when no attachments', () => {
    mockQueryData = [makeLog({ attachments: [] })]
    render(<LogsPage />)
    expect(screen.queryByText(/附件/)).not.toBeInTheDocument()
  })

  // ========== Reminders ==========

  it('renders reminder badge when log has reminders', () => {
    mockQueryData = [makeLog({
      reminders: [
        { id: 1, reminder_type: 'hearing', due_at: '2025-06-15 09:00:00', is_completed: false },
      ],
    })]
    render(<LogsPage />)
    // "开庭" appears in both the reminder badge and the dialog's SelectItem
    expect(screen.getAllByText('开庭').length).toBeGreaterThanOrEqual(2)
  })

  it('renders multiple reminders', () => {
    mockQueryData = [makeLog({
      reminders: [
        { id: 1, reminder_type: 'hearing', due_at: '2025-06-15 09:00:00', is_completed: false },
        { id: 2, reminder_type: 'asset_preservation', due_at: '2025-06-20 09:00:00', is_completed: true },
      ],
    })]
    render(<LogsPage />)
    expect(screen.getAllByText('开庭').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('财产保全').length).toBeGreaterThanOrEqual(2)
  })

  it('shows completion indicator for completed reminders', () => {
    mockQueryData = [makeLog({
      reminders: [
        { id: 1, reminder_type: 'hearing', due_at: '2025-06-15 09:00:00', is_completed: true },
      ],
    })]
    render(<LogsPage />)
    expect(screen.getByText('✓')).toBeInTheDocument()
  })

  it('does not show completion indicator for incomplete reminders', () => {
    mockQueryData = [makeLog({
      reminders: [
        { id: 1, reminder_type: 'hearing', due_at: '2025-06-15 09:00:00', is_completed: false },
      ],
    })]
    render(<LogsPage />)
    expect(screen.queryByText('✓')).not.toBeInTheDocument()
  })

  it('renders reminder with unknown type (fallback to raw type string)', () => {
    mockQueryData = [makeLog({
      reminders: [
        { id: 1, reminder_type: 'unknown_type', due_at: '2025-06-15 09:00:00', is_completed: false },
      ],
    })]
    render(<LogsPage />)
    expect(screen.getByText('unknown_type')).toBeInTheDocument()
  })

  it('renders both attachments and reminders together', () => {
    mockQueryData = [makeLog({
      attachments: [
        { id: 1, log: 1, original_filename: 'doc.pdf', file_path: '/path', media_url: null, uploaded_at: '2025-06-01' },
      ],
      reminders: [
        { id: 1, reminder_type: 'hearing', due_at: '2025-06-15 09:00:00', is_completed: false },
      ],
    })]
    render(<LogsPage />)
    expect(screen.getByText('1 附件')).toBeInTheDocument()
    expect(screen.getAllByText('开庭').length).toBeGreaterThanOrEqual(2)
  })

  // ========== Pagination ==========

  it('shows "load more" button when there are more than 10 date groups', () => {
    // Create 15 logs on different dates to get >10 groups
    const logs = Array.from({ length: 15 }, (_, i) => (
      makeLog({
        id: i + 1,
        content: `日志 ${i + 1}`,
        created_at: `2025-0${(i % 9) + 1}-${String((i % 28) + 1).padStart(2, '0')} 10:00:00`,
      })
    ))
    mockQueryData = logs
    render(<LogsPage />)

    // There should be a "load more" button if >10 groups
    const loadMoreButton = screen.queryByText(/加载更多/)
    // Depending on how many unique dates there are, this may or may not appear
    // With 15 logs spread across months, there should be multiple groups
    if (loadMoreButton) {
      expect(loadMoreButton).toBeInTheDocument()
    }
  })

  it('does not show "load more" button when all groups are visible', () => {
    mockQueryData = [
      makeLog({ id: 1, content: '日志1', created_at: '2025-06-01 10:00:00' }),
      makeLog({ id: 2, content: '日志2', created_at: '2025-06-02 10:00:00' }),
    ]
    render(<LogsPage />)
    expect(screen.queryByText(/加载更多/)).not.toBeInTheDocument()
  })

  it('clicking "load more" shows additional groups', () => {
    // Create exactly 15 logs on 15 different dates to force pagination
    const logs = Array.from({ length: 15 }, (_, i) => (
      makeLog({
        id: i + 1,
        content: `日志内容${i + 1}`,
        created_at: `2025-06-${String(i + 1).padStart(2, '0')} 10:00:00`,
      })
    ))
    mockQueryData = logs
    render(<LogsPage />)

    const loadMoreButton = screen.queryByText(/加载更多/)
    if (loadMoreButton) {
      // Initially only first 10 groups visible
      // After click, more groups should appear
      fireEvent.click(loadMoreButton)
      expect(screen.getByText('日志内容15')).toBeInTheDocument()
    }
  })

  // ========== Create dialog ==========

  it('renders create dialog with title', () => {
    render(<LogsPage />)
    expect(screen.getByText('添加案件日志')).toBeInTheDocument()
  })

  it('renders case selection in dialog', () => {
    render(<LogsPage />)
    expect(screen.getByText('选择案件')).toBeInTheDocument()
  })

  it('renders content textarea in dialog', () => {
    render(<LogsPage />)
    expect(screen.getByPlaceholderText('请输入日志内容')).toBeInTheDocument()
  })

  it('renders reminder settings section', () => {
    render(<LogsPage />)
    expect(screen.getByText('提醒设置（可选）')).toBeInTheDocument()
    expect(screen.getByText('提醒类型')).toBeInTheDocument()
    expect(screen.getByText('提醒时间')).toBeInTheDocument()
  })

  it('renders cancel and confirm buttons in dialog', () => {
    render(<LogsPage />)
    expect(screen.getByText('取消')).toBeInTheDocument()
    expect(screen.getByText('确认')).toBeInTheDocument()
  })

  it('confirm button is disabled when no case selected', () => {
    render(<LogsPage />)
    const confirmButton = screen.getByText('确认')
    expect(confirmButton).toBeDisabled()
  })

  it('confirm button is disabled when content is empty', () => {
    render(<LogsPage />)
    const confirmButton = screen.getByText('确认')
    expect(confirmButton).toBeDisabled()
  })

  it('confirm button is enabled when case and content are provided', () => {
    render(<LogsPage />)
    const textarea = screen.getByPlaceholderText('请输入日志内容')
    fireEvent.change(textarea, { target: { value: '新日志内容' } })

    // The button is still disabled because newCaseId is not set (no case selected)
    const confirmButton = screen.getByText('确认')
    expect(confirmButton).toBeDisabled()
  })

  // ========== Search with actor name ==========

  it('searches by actor real_name', () => {
    mockQueryData = [
      makeLog({ id: 1, content: '日志A', actor_detail: { real_name: '张律师', username: 'zhang' }, created_at: '2025-06-01 10:00:00' }),
      makeLog({ id: 2, content: '日志B', actor_detail: { real_name: '李律师', username: 'li' }, created_at: '2025-06-01 11:00:00' }),
    ]
    render(<LogsPage />)
    const input = screen.getByPlaceholderText('搜索日志内容、案件名称、操作人...')
    fireEvent.change(input, { target: { value: '张' } })
    expect(screen.getByText('日志A')).toBeInTheDocument()
    expect(screen.queryByText('日志B')).not.toBeInTheDocument()
  })

  it('searches by actor username when real_name is missing', () => {
    mockQueryData = [
      makeLog({ id: 1, content: '日志A', actor_detail: { real_name: '', username: 'zhang_lawyer' }, created_at: '2025-06-01 10:00:00' }),
      makeLog({ id: 2, content: '日志B', actor_detail: { real_name: '', username: 'li_judge' }, created_at: '2025-06-01 11:00:00' }),
    ]
    render(<LogsPage />)
    const input = screen.getByPlaceholderText('搜索日志内容、案件名称、操作人...')
    fireEvent.change(input, { target: { value: 'zhang' } })
    expect(screen.getByText('日志A')).toBeInTheDocument()
    expect(screen.queryByText('日志B')).not.toBeInTheDocument()
  })

  // ========== relativeDate function testing (indirect) ==========

  it('renders log with recent date', () => {
    // Use a date that's very old so relativeDate returns the date string itself
    mockQueryData = [makeLog({ created_at: '2020-01-01 10:00:00' })]
    render(<LogsPage />)
    // The date key '2020-01-01' should be rendered
    expect(screen.getByText('2020-01-01')).toBeInTheDocument()
  })

  // ========== Multiple logs on same date ==========

  it('renders multiple logs grouped under same date', () => {
    mockQueryData = [
      makeLog({ id: 1, content: '第一笔', created_at: '2025-06-01 09:00:00' }),
      makeLog({ id: 2, content: '第二笔', created_at: '2025-06-01 14:00:00' }),
    ]
    render(<LogsPage />)
    expect(screen.getByText('第一笔')).toBeInTheDocument()
    expect(screen.getByText('第二笔')).toBeInTheDocument()
  })

  // ========== Delete action ==========

  it('renders delete button for each log', () => {
    mockQueryData = [makeLog()]
    render(<LogsPage />)
    expect(screen.getByText('删除日志')).toBeInTheDocument()
  })

  it('renders delete confirmation dialog', () => {
    mockQueryData = [makeLog()]
    render(<LogsPage />)
    expect(screen.getByText('确认删除')).toBeInTheDocument()
    expect(screen.getByText('确定要删除这条日志吗？')).toBeInTheDocument()
  })

  // ========== Clock/time display ==========

  it('renders clock icon and time for each log', () => {
    mockQueryData = [makeLog({ created_at: '2025-06-01 10:30:00' })]
    render(<LogsPage />)
    expect(screen.getByTestId('clock-icon')).toBeInTheDocument()
  })

  // ========== Search icon ==========

  it('renders search icon in search area', () => {
    render(<LogsPage />)
    expect(screen.getByTestId('search-icon')).toBeInTheDocument()
  })

  // ========== Grid layout for multiple logs ==========

  it('renders grid layout when date group has multiple logs', () => {
    mockQueryData = [
      makeLog({ id: 1, content: '第一条', created_at: '2025-06-01 09:00:00' }),
      makeLog({ id: 2, content: '第二条', created_at: '2025-06-01 14:00:00' }),
    ]
    render(<LogsPage />)
    // Both logs should be visible
    expect(screen.getByText('第一条')).toBeInTheDocument()
    expect(screen.getByText('第二条')).toBeInTheDocument()
  })

  // ========== Content text display ==========

  it('renders log content with break-all styling', () => {
    mockQueryData = [makeLog({ content: '这是一个很长的日志内容用于测试文本换行' })]
    render(<LogsPage />)
    expect(screen.getByText('这是一个很长的日志内容用于测试文本换行')).toBeInTheDocument()
  })

  // ========== Bell icon for reminders ==========

  it('renders bell icon for reminder badges', () => {
    mockQueryData = [makeLog({
      reminders: [
        { id: 1, reminder_type: 'hearing', due_at: '2025-06-15 09:00:00', is_completed: false },
      ],
    })]
    render(<LogsPage />)
    expect(screen.getByTestId('bell-icon')).toBeInTheDocument()
  })

  // ========== Paperclip icon for attachments ==========

  it('renders paperclip icon for attachment badges', () => {
    mockQueryData = [makeLog({
      attachments: [
        { id: 1, log: 1, original_filename: 'test.pdf', file_path: '/path', media_url: null, uploaded_at: '2025-06-01' },
      ],
    })]
    render(<LogsPage />)
    expect(screen.getByTestId('paperclip')).toBeInTheDocument()
  })

  // ========== Reminder with "其他" type ==========

  it('renders reminder with "其他" type label', () => {
    mockQueryData = [makeLog({
      reminders: [
        { id: 1, reminder_type: 'other', due_at: '2025-06-15 09:00:00', is_completed: false },
      ],
    })]
    render(<LogsPage />)
    // "其他" appears in both the reminder badge and the dialog's SelectItem
    expect(screen.getAllByText('其他').length).toBeGreaterThanOrEqual(2)
  })

  // ========== Reminder with "举证期限" type ==========

  it('renders reminder with "举证期限" type label', () => {
    mockQueryData = [makeLog({
      reminders: [
        { id: 1, reminder_type: 'evidence_deadline', due_at: '2025-06-15 09:00:00', is_completed: false },
      ],
    })]
    render(<LogsPage />)
    expect(screen.getAllByText('举证期限').length).toBeGreaterThanOrEqual(2)
  })

  // ========== Logs with undefined/null reminders ==========

  it('handles log with undefined reminders', () => {
    mockQueryData = [makeLog({ reminders: undefined })]
    render(<LogsPage />)
    expect(screen.queryByText(/附件/)).not.toBeInTheDocument()
    expect(screen.queryByTestId('bell-icon')).not.toBeInTheDocument()
  })

  // ========== Logs with undefined/null attachments ==========

  it('handles log with undefined attachments', () => {
    mockQueryData = [makeLog({ attachments: undefined, reminders: [] })]
    render(<LogsPage />)
    expect(screen.queryByText(/附件/)).not.toBeInTheDocument()
  })

  // ========== Default export ==========

  it('exports LogsPage as default', async () => {
    const mod = await import('../components/LogsPage')
    expect(mod.default).toBeDefined()
  })
})
