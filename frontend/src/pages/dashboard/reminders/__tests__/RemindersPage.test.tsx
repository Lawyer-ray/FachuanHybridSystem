import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import RemindersPage from '../index'

vi.mock('@/features/reminders', () => ({
  ReminderList: () => <div data-testid="reminder-list">ReminderList</div>,
}))

describe('RemindersPage', () => {
  it('renders the page title', () => {
    render(
      <MemoryRouter>
        <RemindersPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('重要日期提醒')).toBeInTheDocument()
  })

  it('renders description text', () => {
    render(
      <MemoryRouter>
        <RemindersPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('管理案件和合同的重要时间节点提醒')).toBeInTheDocument()
  })

  it('renders ReminderList component', () => {
    render(
      <MemoryRouter>
        <RemindersPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('reminder-list')).toBeInTheDocument()
  })
})
