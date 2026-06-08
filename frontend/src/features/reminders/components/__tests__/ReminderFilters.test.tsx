vi.mock('../hooks/use-reminder-mutations', () => ({
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
import userEvent from '@testing-library/user-event'
import { ReminderFilters } from '../ReminderFilters'

describe('ReminderFilters', () => {
  const defaultProps = {
    filters: {},
    onFiltersChange: vi.fn(),
    reminderTypes: [
      { value: 'hearing', label: '开庭' },
      { value: 'evidence_deadline', label: '举证到期' },
    ],
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders filter labels', () => {
    render(<ReminderFilters {...defaultProps} />)
    expect(screen.getByText('提醒类型')).toBeInTheDocument()
    expect(screen.getByText('起始日期')).toBeInTheDocument()
    expect(screen.getByText('结束日期')).toBeInTheDocument()
  })

  it('renders clear filter button', () => {
    render(<ReminderFilters {...defaultProps} />)
    expect(screen.getByRole('button', { name: /清除筛选|清除/ })).toBeInTheDocument()
  })

  it('clear button is disabled when no filters active', () => {
    render(<ReminderFilters {...defaultProps} />)
    const clearBtn = screen.getByRole('button', { name: /清除筛选|清除/ })
    expect(clearBtn).toBeDisabled()
  })

  it('clear button is enabled when filters are active', () => {
    render(
      <ReminderFilters
        {...defaultProps}
        filters={{ reminderType: 'hearing' }}
      />,
    )
    const clearBtn = screen.getByRole('button', { name: /清除筛选|清除/ })
    expect(clearBtn).not.toBeDisabled()
  })

  it('calls onFiltersChange when clear is clicked', async () => {
    const user = userEvent.setup()
    const onFiltersChange = vi.fn()
    render(
      <ReminderFilters
        {...defaultProps}
        filters={{ reminderType: 'hearing' }}
        onFiltersChange={onFiltersChange}
      />,
    )
    const clearBtn = screen.getByRole('button', { name: /清除筛选|清除/ })
    await user.click(clearBtn)
    expect(onFiltersChange).toHaveBeenCalledWith({
      reminderType: undefined,
      dateFrom: undefined,
      dateTo: undefined,
    })
  })
})
