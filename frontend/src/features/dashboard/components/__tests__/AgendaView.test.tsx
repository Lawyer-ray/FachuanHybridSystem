import { render, screen } from '@testing-library/react'
import { AgendaView } from '../AgendaView'

vi.mock('@/components/ui/scroll-area', () => ({
  ScrollArea: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => (
    <div {...props}>{children}</div>
  ),
}))

describe('AgendaView', () => {
  const createEvent = (overrides: Record<string, unknown> = {}) => ({
    id: 1,
    time: '09:00',
    title: 'Test Event',
    type_label: '开庭',
    reminder_type: 'hearing' as const,
    courtroom: 'Room 101',
    location: 'Court A',
    lawyer_name: 'John',
    lawyer_names: ['John'],
    is_overdue: false,
    due_at: '2026-06-15T09:00:00Z',
    contract: null,
    case: 1,
    case_log: null,
    ...overrides,
  })

  it('renders empty state when no events', () => {
    render(
      <AgendaView
        eventsByDate={new Map()}
        viewYear={2026}
        viewMonth={5}
        onEventClick={vi.fn()}
      />,
    )
    expect(screen.getByText('本月暂无事件')).toBeInTheDocument()
  })

  it('renders events grouped by date', () => {
    const event = createEvent()
    const eventsByDate = new Map<string, typeof event[]>()
    eventsByDate.set('2026-06-15', [event])

    render(
      <AgendaView
        eventsByDate={eventsByDate}
        viewYear={2026}
        viewMonth={5}
        onEventClick={vi.fn()}
      />,
    )
    expect(screen.getByText('Test Event')).toBeInTheDocument()
    expect(screen.getByText('09:00')).toBeInTheDocument()
    expect(screen.getByText('开庭')).toBeInTheDocument()
  })

  it('filters events by current view month', () => {
    const eventInMonth = createEvent({ id: 1, title: 'June Event' })
    const eventOutOfMonth = createEvent({ id: 2, title: 'July Event' })

    const eventsByDate = new Map<string, typeof eventInMonth[]>()
    eventsByDate.set('2026-06-15', [eventInMonth])
    eventsByDate.set('2026-07-15', [eventOutOfMonth])

    render(
      <AgendaView
        eventsByDate={eventsByDate}
        viewYear={2026}
        viewMonth={5}
        onEventClick={vi.fn()}
      />,
    )
    expect(screen.getByText('June Event')).toBeInTheDocument()
    expect(screen.queryByText('July Event')).not.toBeInTheDocument()
  })

  it('shows overdue badge for overdue events', () => {
    const event = createEvent({ is_overdue: true })
    const eventsByDate = new Map<string, typeof event[]>()
    eventsByDate.set('2026-06-15', [event])

    render(
      <AgendaView
        eventsByDate={eventsByDate}
        viewYear={2026}
        viewMonth={5}
        onEventClick={vi.fn()}
      />,
    )
    expect(screen.getByText('逾期')).toBeInTheDocument()
  })

  it('renders multiple events on same date', () => {
    const event1 = createEvent({ id: 1, title: 'Event A', time: '09:00' })
    const event2 = createEvent({ id: 2, title: 'Event B', time: '14:00' })

    const eventsByDate = new Map<string, typeof event1[]>()
    eventsByDate.set('2026-06-15', [event1, event2])

    render(
      <AgendaView
        eventsByDate={eventsByDate}
        viewYear={2026}
        viewMonth={5}
        onEventClick={vi.fn()}
      />,
    )
    expect(screen.getByText('Event A')).toBeInTheDocument()
    expect(screen.getByText('Event B')).toBeInTheDocument()
  })

  it('renders lawyer name and courtroom', () => {
    const event = createEvent({ lawyer_name: '张律师', courtroom: '第3法庭' })
    const eventsByDate = new Map<string, typeof event[]>()
    eventsByDate.set('2026-06-15', [event])

    render(
      <AgendaView
        eventsByDate={eventsByDate}
        viewYear={2026}
        viewMonth={5}
        onEventClick={vi.fn()}
      />,
    )
    expect(screen.getByText(/张律师/)).toBeInTheDocument()
    expect(screen.getByText(/第3法庭/)).toBeInTheDocument()
  })
})
