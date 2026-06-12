import { render, screen } from '@testing-library/react'
import { ReminderResult } from '../ReminderResult'

vi.mock('@/lib/format', () => ({
  formatAmountInt: (n: number) => `${n}元`,
}))

describe('ReminderResult - branch coverage', () => {
  // Branch: LPR rate list (not interest calculation)
  it('renders LPR rate list items', () => {
    const output = [
      { term: '1年期', rate: '3.45', date: '2026-01-01' },
      { term: '5年期', rate: '3.95', date: '2026-01-01' },
    ]
    render(<ReminderResult input={{}} toolName="lpr_rate" output={output} />)
    expect(screen.getByText('LPR 利率 (2)')).toBeInTheDocument()
    expect(screen.getByText('1年期')).toBeInTheDocument()
    expect(screen.getByText('5年期')).toBeInTheDocument()
  })

  // Branch: LPR rate list with type fallback
  it('renders LPR items using type field fallback', () => {
    const output = [{ type: '1年', rate: '3.45' }]
    render(<ReminderResult input={{}} toolName="get_lpr_rate" output={output} />)
    expect(screen.getByText('1年')).toBeInTheDocument()
  })

  // Branch: LPR rate list with >3 items (sliced to 3)
  it('slices LPR list to 3 items', () => {
    const output = Array.from({ length: 5 }, (_, i) => ({
      term: `Term ${i}`,
      rate: `${3 + i}`,
    }))
    render(<ReminderResult input={{}} toolName="lpr_rate" output={output} />)
    expect(screen.getByText('Term 0')).toBeInTheDocument()
    expect(screen.queryByText('Term 4')).not.toBeInTheDocument()
  })

  // Branch: LPR with no interest/total and no list => null
  it('returns null for LPR with empty output', () => {
    const { container } = render(
      <ReminderResult input={{}} toolName="lpr_rate" output={{}} />,
    )
    expect(container.innerHTML).toBe('')
  })

  // Branch: calculate_interest with interest/total
  it('renders calculate_interest result', () => {
    const output = {
      principal: 100000,
      rate: 3.45,
      days: 365,
      interest: 3450,
      total: 103450,
    }
    render(<ReminderResult input={{}} toolName="calculate_interest" output={output} />)
    expect(screen.getByText('利息计算结果')).toBeInTheDocument()
    expect(screen.getByText('100000元')).toBeInTheDocument()
    expect(screen.getByText(/3\.45%/)).toBeInTheDocument()
    expect(screen.getByText('365')).toBeInTheDocument()
    expect(screen.getByText('3450元')).toBeInTheDocument()
    expect(screen.getByText('103450元')).toBeInTheDocument()
  })

  // Branch: calculate_interest with only total (no interest)
  it('renders calculate_interest with only total', () => {
    const output = { total: 50000 }
    render(<ReminderResult input={{}} toolName="calculate_interest" output={output} />)
    expect(screen.getByText('利息计算结果')).toBeInTheDocument()
    expect(screen.getByText('50000元')).toBeInTheDocument()
  })

  // Branch: create_new_reminder shows SingleReminder
  it('renders SingleReminder for create_new_reminder', () => {
    const output = { title: 'New Task', priority: 'urgent' }
    render(<ReminderResult input={{}} toolName="create_new_reminder" output={output} />)
    expect(screen.getByText('New Task')).toBeInTheDocument()
    expect(screen.getByText('紧急')).toBeInTheDocument()
  })

  // Branch: update_reminder shows SingleReminder
  it('renders SingleReminder for update_reminder', () => {
    const output = { title: 'Updated Task', remind_at: '2026-06-15 10:00' }
    render(<ReminderResult input={{}} toolName="update_reminder" output={output} />)
    expect(screen.getByText('Updated Task')).toBeInTheDocument()
    expect(screen.getByText('2026-06-15 10:00')).toBeInTheDocument()
  })

  // Branch: SingleReminder with all fields
  it('renders SingleReminder with all optional fields', () => {
    const output = {
      title: 'Full Reminder',
      priority: 'low',
      reminder_type: 'hearing',
      due_date: '2026-07-01',
      remind_at: '2026-06-30 09:00',
    }
    render(<ReminderResult input={{}} toolName="get_reminder" output={output} />)
    expect(screen.getByText('Full Reminder')).toBeInTheDocument()
    expect(screen.getByText('hearing')).toBeInTheDocument()
    expect(screen.getByText('2026-07-01')).toBeInTheDocument()
    expect(screen.getByText('2026-06-30 09:00')).toBeInTheDocument()
  })

  // Branch: SingleReminder name fallback
  it('uses name field as fallback for title', () => {
    const output = { name: 'Name Fallback', priority: 'high' }
    render(<ReminderResult input={{}} toolName="get_reminder" output={output} />)
    expect(screen.getByText('Name Fallback')).toBeInTheDocument()
  })

  // Branch: list reminders with >5 items
  it('shows overflow text for >5 reminders', () => {
    const output = {
      results: Array.from({ length: 7 }, (_, i) => ({
        title: `Reminder ${i}`,
        priority: 'low',
      })),
    }
    render(<ReminderResult input={{}} toolName="list_reminders" output={output} />)
    expect(screen.getByText(/还有 2 个/)).toBeInTheDocument()
  })

  // Branch: CompactReminder with due_date
  it('renders CompactReminder with due_date', () => {
    const output = {
      results: [
        { title: 'Task A', priority: 'high', due_date: '2026-06-15' },
      ],
    }
    render(<ReminderResult input={{}} toolName="list_reminders" output={output} />)
    expect(screen.getByText('Task A')).toBeInTheDocument()
    expect(screen.getByText('2026-06-15')).toBeInTheDocument()
  })

  // Branch: CompactReminder with name fallback
  it('renders CompactReminder with name fallback', () => {
    const output = {
      results: [{ name: 'Compact Name', priority: 'low' }],
    }
    render(<ReminderResult input={{}} toolName="list_reminders" output={output} />)
    expect(screen.getByText('Compact Name')).toBeInTheDocument()
  })

  // Branch: extractList with items key
  it('extracts list from items key', () => {
    const output = { items: [{ title: 'Item A' }] }
    render(<ReminderResult input={{}} toolName="list_reminders" output={output} />)
    expect(screen.getByText('共 1 个提醒')).toBeInTheDocument()
  })

  // Branch: extractList with data key
  it('extracts list from data key', () => {
    const output = { data: [{ title: 'Data A' }, { title: 'Data B' }] }
    render(<ReminderResult input={{}} toolName="list_reminders" output={output} />)
    expect(screen.getByText('共 2 个提醒')).toBeInTheDocument()
  })

  // Branch: extractList with list key
  it('extracts list from list key', () => {
    const output = { list: [{ title: 'List A' }] }
    render(<ReminderResult input={{}} toolName="list_reminders" output={output} />)
    expect(screen.getByText('共 1 个提醒')).toBeInTheDocument()
  })

  // Branch: non-object/non-array output => empty list
  it('returns empty for string output', () => {
    render(<ReminderResult input={{}} toolName="list_reminders" output="invalid" />)
    expect(screen.getByText('未找到提醒')).toBeInTheDocument()
  })

  // Branch: LPR with date field
  it('renders LPR item with date field', () => {
    const output = [{ term: '1年', rate: '3.45', date: '2026-01' }]
    render(<ReminderResult input={{}} toolName="lpr_rate" output={output} />)
    expect(screen.getByText('2026-01')).toBeInTheDocument()
  })

  // Branch: LPR with empty term and rate
  it('renders LPR item with empty term and rate', () => {
    const output = [{}]
    render(<ReminderResult input={{}} toolName="lpr_rate" output={output} />)
    expect(screen.getByText('LPR 利率 (1)')).toBeInTheDocument()
  })

  // Branch: CompactReminder with empty priority (not urgent)
  it('renders CompactReminder with empty priority', () => {
    const output = {
      results: [{ title: 'Normal Task', priority: '' }],
    }
    render(<ReminderResult input={{}} toolName="list_reminders" output={output} />)
    expect(screen.getByText('Normal Task')).toBeInTheDocument()
  })

  // Branch: FinanceStats renders all object entries
  it('renders FinanceStats with multiple entries', () => {
    const output = {
      total_income: 100000,
      total_expense: 60000,
      net_profit: 40000,
    }
    render(<ReminderResult input={{}} toolName="get_finance_stats" output={output} />)
    expect(screen.getByText('财务统计')).toBeInTheDocument()
    expect(screen.getByText(/total_income/)).toBeInTheDocument()
    expect(screen.getByText(/net_profit/)).toBeInTheDocument()
  })
})
