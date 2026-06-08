vi.mock('../../hooks/use-reminders', () => ({
  useReminders: vi.fn(),
  useReminderTypes: vi.fn(),
}))

vi.mock('../../hooks/use-reminder-mutations', () => ({
  useReminderMutations: () => ({
    deleteMutation: { mutate: vi.fn(), isPending: false },
    createMutation: { mutate: vi.fn(), isPending: false },
    updateMutation: { mutate: vi.fn(), isPending: false },
  }),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

import { render, screen } from '@testing-library/react'
import { ReminderList } from '../ReminderList'
import { useReminders, useReminderTypes } from '../../hooks/use-reminders'

describe('ReminderList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useReminderTypes).mockReturnValue({ data: [] } as any)
  })

  it('renders loading skeleton when loading', () => {
    vi.mocked(useReminders).mockReturnValue({
      data: [], isLoading: true, isError: false, error: null,
    } as any)
    render(<ReminderList />)
    expect(screen.getByTestId('loading-skeleton')).toBeInTheDocument()
  })

  it('renders error state on error', () => {
    vi.mocked(useReminders).mockReturnValue({
      data: [], isLoading: false, isError: true, error: new Error('Network error'), refetch: vi.fn(),
    } as any)
    render(<ReminderList />)
    expect(screen.getByTestId('error-state')).toBeInTheDocument()
    expect(screen.getByText('加载失败')).toBeInTheDocument()
  })

  it('renders empty state when no reminders', () => {
    vi.mocked(useReminders).mockReturnValue({
      data: [], isLoading: false, isError: false, error: null,
    } as any)
    render(<ReminderList />)
    expect(screen.getByTestId('empty-state')).toBeInTheDocument()
    expect(screen.getByText('暂无提醒')).toBeInTheDocument()
  })

  it('renders reminders in table', () => {
    vi.mocked(useReminders).mockReturnValue({
      data: [{
        id: 1, reminder_type: 'hearing', reminder_type_label: '开庭',
        content: 'Test reminder', due_at: '2026-12-01T09:00:00Z',
        contract: 1, case: null, case_log: null, metadata: {}, created_at: '2026-01-01T00:00:00Z',
      }],
      isLoading: false, isError: false, error: null,
    } as any)
    render(<ReminderList />)
    expect(screen.getAllByText('Test reminder').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('新建提醒')).toBeInTheDocument()
  })

  it('shows empty state when filtered results are empty', () => {
    vi.mocked(useReminders).mockReturnValue({
      data: [], isLoading: false, isError: false, error: null,
    } as any)
    render(<ReminderList />)
    expect(screen.getByText('暂无提醒')).toBeInTheDocument()
  })
})
