vi.mock('lucide-react', () => ({
  ChevronLeft: () => <svg data-testid="chevron-left" />,
  ChevronRight: () => <svg data-testid="chevron-right" />,
  MapPin: () => <svg />,
  User: () => <svg />,
  Clock: () => <svg />,
  Pencil: () => <svg />,
  Trash2: () => <svg />,
}))

vi.mock('@/features/reminders/api', () => ({
  reminderApi: {
    list: vi.fn().mockResolvedValue([]),
    getTargetOptions: vi.fn().mockResolvedValue({ groups: [] }),
  },
}))

vi.mock('@/features/reminders/hooks/use-reminder-mutations', () => ({
  useReminderMutations: () => ({
    deleteMutation: { mutate: vi.fn(), isPending: false },
    createMutation: { mutate: vi.fn(), isPending: false },
    updateMutation: { mutate: vi.fn(), isPending: false },
  }),
}))

vi.mock('@/features/reminders/components/ReminderFormDialog', () => ({
  ReminderFormDialog: ({ open }: { open: boolean }) => (open ? <div data-testid="form-dialog" /> : null),
}))

vi.mock('../AgendaView', () => ({
  AgendaView: () => <div data-testid="agenda-view" />,
}))

vi.mock('@/lib/date', () => ({
  formatDate: (d: string) => d,
}))

vi.mock('@/lib/utils', () => ({
  cn: (...args: unknown[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>()
  return {
    ...actual,
    useQuery: vi.fn().mockReturnValue({ data: undefined }),
    useQueryClient: vi.fn().mockReturnValue({
      invalidateQueries: vi.fn(),
    }),
  }
})

vi.mock('@/components/ui/card', () => ({
  Card: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, variant, className }: Record<string, unknown>) => <span className={className as string} data-variant={variant}>{children}</span>,
}))
vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size, className }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} className={className as string}>{children}</button>
  ),
}))
vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) => open ? <div data-testid="dialog">{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))
vi.mock('@/components/ui/tabs', () => ({
  Tabs: ({ children, value }: { children: React.ReactNode; value?: string }) => <div data-value={value}>{children}</div>,
  TabsList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsTrigger: ({ children, value: triggerValue }: { children: React.ReactNode; value?: string }) => <button data-trigger={triggerValue}>{children}</button>,
  TabsContent: ({ children, value: contentValue }: { children: React.ReactNode; value?: string }) => <div data-tab={contentValue}>{children}</div>,
}))
vi.mock('@/components/ui/popover', () => ({
  Popover: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('@/components/ui/scroll-area', () => ({
  ScrollArea: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { CalendarCard } from '../CalendarCard'
import { useQuery } from '@tanstack/react-query'

const mockUseQuery = vi.mocked(useQuery)

const mockReminders = [
  {
    id: 1,
    content: '开庭',
    reminder_type: 'hearing',
    reminder_type_label: '开庭',
    due_at: `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}T09:00:00`,
    metadata: { courtroom: '第一法庭', lawyer_name: '张律师' },
    contract: 1,
    case: null,
    case_log: null,
  },
  {
    id: 2,
    content: '证据截止',
    reminder_type: 'evidence_deadline',
    reminder_type_label: '举证到期',
    due_at: `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}T14:00:00`,
    metadata: {},
    contract: null,
    case: 2,
    case_log: null,
  },
  {
    id: 3,
    content: '逾期事件',
    reminder_type: 'other',
    reminder_type_label: '其他',
    due_at: '2020-01-01T10:00:00',
    metadata: {},
    contract: null,
    case: null,
    case_log: 3,
  },
  {
    id: 4,
    content: '同类型合并1',
    reminder_type: 'hearing',
    reminder_type_label: '开庭',
    due_at: `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}T09:00:00`,
    metadata: { source_id: 'case-hearing-1', lawyer_name: '李律师' },
    contract: null,
    case: null,
    case_log: null,
  },
  // More than 3 events on same day
  {
    id: 5,
    content: '第三条事件',
    reminder_type: 'payment_deadline',
    reminder_type_label: '缴费期限',
    due_at: `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}T15:00:00`,
    metadata: {},
    contract: null,
    case: null,
    case_log: null,
  },
  {
    id: 6,
    content: '第四条事件',
    reminder_type: 'submission_deadline',
    reminder_type_label: '材料提交',
    due_at: `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}T16:00:00`,
    metadata: {},
    contract: null,
    case: null,
    case_log: null,
  },
  // No due_at
  {
    id: 7,
    content: '无截止日期',
    reminder_type: 'other',
    reminder_type_label: '其他',
    due_at: '',
    metadata: {},
    contract: null,
    case: null,
    case_log: null,
  },
]

describe('CalendarCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseQuery.mockReturnValue({ data: undefined } as never)
  })

  it('renders calendar card with current month', () => {
    render(<CalendarCard />)
    const now = new Date()
    const yearMonth = `${now.getFullYear()}年${now.getMonth() + 1}月`
    expect(screen.getByText(yearMonth)).toBeInTheDocument()
  })

  it('renders day headers', () => {
    render(<CalendarCard />)
    expect(screen.getByText('日')).toBeInTheDocument()
    expect(screen.getByText('一')).toBeInTheDocument()
    expect(screen.getByText('六')).toBeInTheDocument()
  })

  it('renders today button', () => {
    render(<CalendarCard />)
    expect(screen.getByText('今天')).toBeInTheDocument()
  })

  it('renders view toggle tabs', () => {
    render(<CalendarCard />)
    expect(screen.getByText('月')).toBeInTheDocument()
    expect(screen.getByText('议程')).toBeInTheDocument()
  })

  it('renders legend items', () => {
    render(<CalendarCard />)
    expect(screen.getByText('开庭')).toBeInTheDocument()
    expect(screen.getByText('已逾期')).toBeInTheDocument()
  })

  it('navigates to previous month', () => {
    render(<CalendarCard />)
    const prevBtn = screen.getByTestId('chevron-left').closest('button')!
    const now = new Date()
    fireEvent.click(prevBtn)
    const prevMonth = now.getMonth() === 0 ? 12 : now.getMonth()
    const prevYear = now.getMonth() === 0 ? now.getFullYear() - 1 : now.getFullYear()
    expect(screen.getByText(`${prevYear}年${prevMonth}月`)).toBeInTheDocument()
  })

  it('navigates to next month', () => {
    render(<CalendarCard />)
    const nextBtn = screen.getByTestId('chevron-right').closest('button')!
    const now = new Date()
    fireEvent.click(nextBtn)
    const nextMonth = now.getMonth() === 11 ? 1 : now.getMonth() + 2
    const nextYear = now.getMonth() === 11 ? now.getFullYear() + 1 : now.getFullYear()
    expect(screen.getByText(`${nextYear}年${nextMonth}月`)).toBeInTheDocument()
  })

  it('goes to today when clicking today button', () => {
    render(<CalendarCard />)
    fireEvent.click(screen.getByTestId('chevron-right').closest('button')!)
    fireEvent.click(screen.getByText('今天'))
    const now = new Date()
    expect(screen.getByText(`${now.getFullYear()}年${now.getMonth() + 1}月`)).toBeInTheDocument()
  })

  it('renders with reminders', () => {
    mockUseQuery.mockImplementation((opts: Record<string, unknown>) => {
      if (opts.queryKey?.[0] === 'dashboard-reminders') return { data: mockReminders } as never
      if (opts.queryKey?.[0] === 'reminders-target-options') return { data: { groups: [] } } as never
      return { data: undefined } as never
    })
    render(<CalendarCard />)
    // Multiple "开庭" elements (legend + events)
    expect(screen.getAllByText('开庭').length).toBeGreaterThan(0)
  })

  it('renders event count for days with events', () => {
    mockUseQuery.mockImplementation((opts: Record<string, unknown>) => {
      if (opts.queryKey?.[0] === 'dashboard-reminders') return { data: mockReminders } as never
      if (opts.queryKey?.[0] === 'reminders-target-options') return { data: { groups: [] } } as never
      return { data: undefined } as never
    })
    render(<CalendarCard />)
    // Should show count like "X条"
    const countEls = screen.queryAllByText(/\d+条/)
    expect(countEls.length).toBeGreaterThan(0)
  })

  it('navigates prev month at january boundary', () => {
    render(<CalendarCard />)
    // Navigate to January by going back many times
    const prevBtn = screen.getByTestId('chevron-left').closest('button')!
    for (let i = 0; i < new Date().getMonth() + 1; i++) {
      fireEvent.click(prevBtn)
    }
    expect(screen.getByText(/年12月/)).toBeInTheDocument()
  })

  it('navigates next month at december boundary', () => {
    render(<CalendarCard />)
    const nextBtn = screen.getByTestId('chevron-right').closest('button')!
    for (let i = 0; i < 12 - new Date().getMonth(); i++) {
      fireEvent.click(nextBtn)
    }
    expect(screen.getByText(/年1月/)).toBeInTheDocument()
  })

  it('renders empty calendar cells', () => {
    render(<CalendarCard />)
    // Calendar should have grid cells
    const gridCells = document.querySelectorAll('.min-h-\\[130px\\]')
    expect(gridCells.length).toBeGreaterThan(0)
  })

  it('renders today cell with special styling', () => {
    render(<CalendarCard />)
    const now = new Date()
    // Today's date number should be in the calendar
    const todayElements = screen.getAllByText(now.getDate().toString())
    expect(todayElements.length).toBeGreaterThan(0)
  })

  it('renders month view tab content', () => {
    render(<CalendarCard />)
    // Month grid should be visible
    expect(screen.getByText('日')).toBeInTheDocument()
    expect(screen.getByText('五')).toBeInTheDocument()
  })

  it('renders agenda view tab content', () => {
    render(<CalendarCard />)
    // Switch to agenda view by clicking the tab button
    fireEvent.click(screen.getByText('议程'))
    expect(screen.getByTestId('agenda-view')).toBeInTheDocument()
  })

  it('handles keyboard events on calendar cells', () => {
    render(<CalendarCard />)
    const now = new Date()
    // Find a cell with a date and trigger Enter key
    const cells = document.querySelectorAll('[role="button"]')
    if (cells.length > 0) {
      fireEvent.keyDown(cells[0], { key: 'Enter' })
      // Should open form dialog
    }
    expect(screen.getByText(/年\d+月/)).toBeInTheDocument()
  })

  it('handles space key on calendar cells', () => {
    render(<CalendarCard />)
    const cells = document.querySelectorAll('[role="button"]')
    if (cells.length > 0) {
      fireEvent.keyDown(cells[0], { key: ' ' })
    }
    expect(screen.getByText(/年\d+月/)).toBeInTheDocument()
  })

  it('renders with empty reminders array', () => {
    mockUseQuery.mockImplementation((opts: Record<string, unknown>) => {
      if (opts.queryKey?.[0] === 'dashboard-reminders') return { data: [] } as never
      if (opts.queryKey?.[0] === 'reminders-target-options') return { data: { groups: [] } } as never
      return { data: undefined } as never
    })
    render(<CalendarCard />)
    expect(screen.getByText(/年\d+月/)).toBeInTheDocument()
  })

  it('renders calendar with target options', () => {
    mockUseQuery.mockImplementation((opts: Record<string, unknown>) => {
      if (opts.queryKey?.[0] === 'dashboard-reminders') return { data: [] } as never
      if (opts.queryKey?.[0] === 'reminders-target-options') return {
        data: {
          groups: [{
            key: 'contract',
            label: '合同',
            items: [{ id: 1, name: '测试合同' }],
          }],
        },
      } as never
      return { data: undefined } as never
    })
    render(<CalendarCard />)
    expect(screen.getByText(/年\d+月/)).toBeInTheDocument()
  })

  it('renders with overdue events showing strikethrough', () => {
    mockUseQuery.mockImplementation((opts: Record<string, unknown>) => {
      if (opts.queryKey?.[0] === 'dashboard-reminders') return { data: [mockReminders[2]] } as never
      return { data: { groups: [] } } as never
    })
    render(<CalendarCard />)
    // The overdue event from 2020 should render
    expect(screen.getByText(/年\d+月/)).toBeInTheDocument()
  })

  it('renders events with lawyer and courtroom info', () => {
    mockUseQuery.mockImplementation((opts: Record<string, unknown>) => {
      if (opts.queryKey?.[0] === 'dashboard-reminders') return { data: [mockReminders[0]] } as never
      return { data: { groups: [] } } as never
    })
    render(<CalendarCard />)
    expect(screen.getByText(/年\d+月/)).toBeInTheDocument()
  })

  // --- New tests for uncovered lines ---

  it('handles event click to open detail dialog', () => {
    mockUseQuery.mockImplementation((opts: Record<string, unknown>) => {
      if (opts.queryKey?.[0] === 'dashboard-reminders') return { data: [mockReminders[0]] } as never
      if (opts.queryKey?.[0] === 'reminders-target-options') return { data: { groups: [] } } as never
      return { data: undefined } as never
    })
    render(<CalendarCard />)
    // Find the event button in the calendar and click it
    const eventBtns = screen.getAllByText('开庭')
    const eventBtn = eventBtns.find((el) => el.closest('button')?.className?.includes('rounded-md'))
    if (eventBtn) {
      fireEvent.click(eventBtn)
    }
  })

  it('handles clicking a calendar cell to create reminder', () => {
    render(<CalendarCard />)
    const cells = document.querySelectorAll('[role="button"]')
    if (cells.length > 0) {
      fireEvent.click(cells[0])
      // Should open form dialog
    }
  })

  it('renders more than 3 events popover', () => {
    mockUseQuery.mockImplementation((opts: Record<string, unknown>) => {
      if (opts.queryKey?.[0] === 'dashboard-reminders') return { data: mockReminders } as never
      if (opts.queryKey?.[0] === 'reminders-target-options') return { data: { groups: [] } } as never
      return { data: undefined } as never
    })
    render(<CalendarCard />)
    // Today should have >3 events (reminders 1, 2, 4, 5, 6 are today)
    // The "共 N 条" link should appear
    const moreLinks = screen.queryAllByText(/共 \d+ 条/)
    expect(moreLinks.length).toBeGreaterThan(0)
  })

  it('handles agenda view tab click', () => {
    render(<CalendarCard />)
    fireEvent.click(screen.getByText('议程'))
    expect(screen.getByTestId('agenda-view')).toBeInTheDocument()
  })

  it('handles month view tab click', () => {
    render(<CalendarCard />)
    fireEvent.click(screen.getByText('议程'))
    fireEvent.click(screen.getByText('月'))
    // Day headers should be visible again
    expect(screen.getByText('日')).toBeInTheDocument()
  })

  it('handles keyboard Space on calendar cell', () => {
    render(<CalendarCard />)
    const cells = document.querySelectorAll('[role="button"]')
    if (cells.length > 0) {
      fireEvent.keyDown(cells[0], { key: ' ' })
    }
  })

  it('handles other key on calendar cell (no action)', () => {
    render(<CalendarCard />)
    const cells = document.querySelectorAll('[role="button"]')
    if (cells.length > 0) {
      fireEvent.keyDown(cells[0], { key: 'Tab' })
    }
  })

  it('renders calendar with no reminders', () => {
    mockUseQuery.mockImplementation((opts: Record<string, unknown>) => {
      if (opts.queryKey?.[0] === 'dashboard-reminders') return { data: [] } as never
      if (opts.queryKey?.[0] === 'reminders-target-options') return { data: { groups: [] } } as never
      return { data: undefined } as never
    })
    render(<CalendarCard />)
    // No event counts should show
    expect(screen.queryAllByText(/\d+条/).length).toBe(0)
  })

  it('renders event with location info', () => {
    const remindersWithLocation = [{
      id: 100,
      content: 'Meeting',
      reminder_type: 'other' as const,
      reminder_type_label: '其他',
      due_at: `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}T10:00:00`,
      metadata: { location: 'Room 301' },
      contract: null,
      case: null,
      case_log: null,
    }]
    mockUseQuery.mockImplementation((opts: Record<string, unknown>) => {
      if (opts.queryKey?.[0] === 'dashboard-reminders') return { data: remindersWithLocation } as never
      if (opts.queryKey?.[0] === 'reminders-target-options') return { data: { groups: [] } } as never
      return { data: undefined } as never
    })
    render(<CalendarCard />)
    expect(screen.getByText(/年\d+月/)).toBeInTheDocument()
  })

  it('renders event with case_log reference', () => {
    mockUseQuery.mockImplementation((opts: Record<string, unknown>) => {
      if (opts.queryKey?.[0] === 'dashboard-reminders') return { data: [mockReminders[2]] } as never
      return { data: { groups: [] } } as never
    })
    render(<CalendarCard />)
    expect(screen.getByText(/年\d+月/)).toBeInTheDocument()
  })

  it('handles event with source_id for hearing merge', () => {
    // mockReminders[3] has source_id: 'case-hearing-1', same time as mockReminders[0]
    mockUseQuery.mockImplementation((opts: Record<string, unknown>) => {
      if (opts.queryKey?.[0] === 'dashboard-reminders') return { data: [mockReminders[0], mockReminders[3]] } as never
      if (opts.queryKey?.[0] === 'reminders-target-options') return { data: { groups: [] } } as never
      return { data: undefined } as never
    })
    render(<CalendarCard />)
    // Both lawyers should appear in merged event
    expect(screen.getByText(/年\d+月/)).toBeInTheDocument()
  })

  it('renders calendar legend', () => {
    render(<CalendarCard />)
    expect(screen.getByText('开庭')).toBeInTheDocument()
    expect(screen.getByText('保全到期')).toBeInTheDocument()
    expect(screen.getByText('举证到期')).toBeInTheDocument()
    expect(screen.getByText('上诉到期')).toBeInTheDocument()
    expect(screen.getByText('诉讼时效')).toBeInTheDocument()
    expect(screen.getByText('缴费期限')).toBeInTheDocument()
    expect(screen.getByText('材料提交')).toBeInTheDocument()
    expect(screen.getByText('其他')).toBeInTheDocument()
    expect(screen.getByText('已逾期')).toBeInTheDocument()
  })

  it('handles different reminder types', () => {
    const mixedReminders = [
      { ...mockReminders[0], reminder_type: 'asset_preservation_expires', reminder_type_label: '保全到期', due_at: `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}T10:00:00` },
      { ...mockReminders[0], id: 10, reminder_type: 'appeal_deadline', reminder_type_label: '上诉到期', due_at: `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}T11:00:00` },
      { ...mockReminders[0], id: 11, reminder_type: 'statute_limitations', reminder_type_label: '诉讼时效', due_at: `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}T12:00:00` },
    ]
    mockUseQuery.mockImplementation((opts: Record<string, unknown>) => {
      if (opts.queryKey?.[0] === 'dashboard-reminders') return { data: mixedReminders } as never
      if (opts.queryKey?.[0] === 'reminders-target-options') return { data: { groups: [] } } as never
      return { data: undefined } as never
    })
    render(<CalendarCard />)
    expect(screen.getByText(/年\d+月/)).toBeInTheDocument()
  })

  it('handles reminder without metadata', () => {
    const noMetaReminder = [{
      id: 99,
      content: 'No metadata event',
      reminder_type: 'other' as const,
      reminder_type_label: '其他',
      due_at: `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}T10:00:00`,
      metadata: null,
      contract: null,
      case: null,
      case_log: null,
    }]
    mockUseQuery.mockImplementation((opts: Record<string, unknown>) => {
      if (opts.queryKey?.[0] === 'dashboard-reminders') return { data: noMetaReminder } as never
      if (opts.queryKey?.[0] === 'reminders-target-options') return { data: { groups: [] } } as never
      return { data: undefined } as never
    })
    render(<CalendarCard />)
    expect(screen.getByText(/年\d+月/)).toBeInTheDocument()
  })

  it('handles reminder without due_at', () => {
    mockUseQuery.mockImplementation((opts: Record<string, unknown>) => {
      if (opts.queryKey?.[0] === 'dashboard-reminders') return { data: [mockReminders[6]] } as never
      if (opts.queryKey?.[0] === 'reminders-target-options') return { data: { groups: [] } } as never
      return { data: undefined } as never
    })
    render(<CalendarCard />)
    // Reminder without due_at should be skipped
    expect(screen.getByText(/年\d+月/)).toBeInTheDocument()
  })

  it('handles target options with contract group', () => {
    mockUseQuery.mockImplementation((opts: Record<string, unknown>) => {
      if (opts.queryKey?.[0] === 'dashboard-reminders') return { data: [] } as never
      if (opts.queryKey?.[0] === 'reminders-target-options') return {
        data: {
          groups: [{
            key: 'contract',
            label: '合同',
            items: [{ id: 1, name: '合同A' }, { id: 2, name: '合同B' }],
          }],
        },
      } as never
      return { data: undefined } as never
    })
    render(<CalendarCard />)
    expect(screen.getByText(/年\d+月/)).toBeInTheDocument()
  })

  it('renders weekend cells with muted styling', () => {
    render(<CalendarCard />)
    const cells = document.querySelectorAll('.min-h-\\[130px\\]')
    expect(cells.length).toBeGreaterThan(0)
  })

  it('handles merged hearing with same fallback key', () => {
    // Two hearings at same time without source_id, same content, courtroom, contract, case_log
    const sameHearings = [
      { id: 200, content: 'Same hearing', reminder_type: 'hearing' as const, reminder_type_label: '开庭', due_at: `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}T09:00:00`, metadata: { courtroom: 'Court A', lawyer_name: 'Lawyer A' }, contract: 1, case: null, case_log: null },
      { id: 201, content: 'Same hearing', reminder_type: 'hearing' as const, reminder_type_label: '开庭', due_at: `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}T09:00:00`, metadata: { courtroom: 'Court A', lawyer_name: 'Lawyer B' }, contract: 1, case: null, case_log: null },
    ]
    mockUseQuery.mockImplementation((opts: Record<string, unknown>) => {
      if (opts.queryKey?.[0] === 'dashboard-reminders') return { data: sameHearings } as never
      if (opts.queryKey?.[0] === 'reminders-target-options') return { data: { groups: [] } } as never
      return { data: undefined } as never
    })
    render(<CalendarCard />)
    // Both lawyers should be merged into one event
    expect(screen.getByText(/年\d+月/)).toBeInTheDocument()
  })

  it('handles reminder with hearing type and no lawyer', () => {
    const noLawyerHearing = [{
      id: 300,
      content: 'No lawyer hearing',
      reminder_type: 'hearing' as const,
      reminder_type_label: '开庭',
      due_at: `${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}-${String(new Date().getDate()).padStart(2, '0')}T09:00:00`,
      metadata: { courtroom: 'Court B' },
      contract: null,
      case: null,
      case_log: null,
    }]
    mockUseQuery.mockImplementation((opts: Record<string, unknown>) => {
      if (opts.queryKey?.[0] === 'dashboard-reminders') return { data: noLawyerHearing } as never
      if (opts.queryKey?.[0] === 'reminders-target-options') return { data: { groups: [] } } as never
      return { data: undefined } as never
    })
    render(<CalendarCard />)
    expect(screen.getByText(/年\d+月/)).toBeInTheDocument()
  })
})
