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
  ReminderFormDialog: ({ open }: any) => (open ? <div data-testid="form-dialog" /> : null),
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

import { render, screen } from '@testing-library/react'
import { CalendarCard } from '../CalendarCard'

describe('CalendarCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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
})
