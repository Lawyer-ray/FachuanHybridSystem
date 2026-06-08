import { render, screen } from '@testing-library/react'
import { ReminderResult } from '../ReminderResult'

vi.mock('@/lib/format', () => ({
  formatAmountInt: (n: number) => `${n}元`,
}))

describe('ReminderResult', () => {
  const baseProps = {
    input: {},
    toolName: 'list_reminders',
  }

  it('renders "未找到提醒" when output is empty', () => {
    render(<ReminderResult {...baseProps} output={[]} />)
    expect(screen.getByText('未找到提醒')).toBeInTheDocument()
  })

  it('renders reminder count for list results', () => {
    const output = {
      results: [
        { title: 'Reminder A', priority: 'high' },
        { title: 'Reminder B', priority: 'low' },
      ],
    }
    render(<ReminderResult {...baseProps} output={output} />)
    expect(screen.getByText('共 2 个提醒')).toBeInTheDocument()
  })

  it('renders single reminder for get_reminder', () => {
    const output = {
      title: 'Court Hearing',
      reminder_type: 'hearing',
      due_date: '2026-06-20',
    }
    render(<ReminderResult input={{}} toolName="get_reminder" output={output} />)
    expect(screen.getByText('Court Hearing')).toBeInTheDocument()
    expect(screen.getByText('2026-06-20')).toBeInTheDocument()
  })

  it('shows "紧急" badge for high priority', () => {
    const output = {
      title: 'Urgent Task',
      priority: 'high',
    }
    render(<ReminderResult input={{}} toolName="get_reminder" output={output} />)
    expect(screen.getByText('紧急')).toBeInTheDocument()
  })

  it('renders LPR interest calculation result', () => {
    const output = {
      principal: 100000,
      rate: 3.45,
      days: 365,
      interest: 3450,
      total: 103450,
    }
    render(<ReminderResult input={{}} toolName="calculate_interest" output={output} />)
    expect(screen.getByText('利息计算结果')).toBeInTheDocument()
    expect(screen.getByText('3450元')).toBeInTheDocument()
  })

  it('renders finance stats', () => {
    const output = {
      total_income: 50000,
      total_expense: 30000,
    }
    render(<ReminderResult input={{}} toolName="get_finance_stats" output={output} />)
    expect(screen.getByText('财务统计')).toBeInTheDocument()
  })

  it('shows "未命名提醒" when name is missing', () => {
    render(<ReminderResult input={{}} toolName="get_reminder" output={{}} />)
    expect(screen.getByText('未命名提醒')).toBeInTheDocument()
  })
})
