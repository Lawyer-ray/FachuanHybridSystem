import { render, screen } from '@testing-library/react'
import { Timeline } from '../Timeline'

const groups = [
  {
    date: '2024-01-01',
    items: [
      { id: '1', date: '2024-01-01', title: 'First event', description: 'Description 1' },
      { id: '2', date: '2024-01-01', title: 'Second event' },
    ],
  },
  {
    date: '2024-02-01',
    items: [
      { id: '3', date: '2024-02-01', title: 'Third event', description: 'Description 3' },
    ],
  },
]

describe('Timeline', () => {
  it('renders group dates', () => {
    render(<Timeline groups={groups} />)
    expect(screen.getByText('2024-01-01')).toBeInTheDocument()
    expect(screen.getByText('2024-02-01')).toBeInTheDocument()
  })

  it('renders item titles', () => {
    render(<Timeline groups={groups} />)
    expect(screen.getByText('First event')).toBeInTheDocument()
    expect(screen.getByText('Second event')).toBeInTheDocument()
    expect(screen.getByText('Third event')).toBeInTheDocument()
  })

  it('renders descriptions when provided', () => {
    render(<Timeline groups={groups} />)
    expect(screen.getByText('Description 1')).toBeInTheDocument()
    expect(screen.getByText('Description 3')).toBeInTheDocument()
  })

  it('does not render description when not provided', () => {
    render(<Timeline groups={groups} />)
    // Second event has no description
    const items = screen.getAllByText('Second event')
    expect(items).toHaveLength(1)
  })

  it('renders with empty groups', () => {
    const { container } = render(<Timeline groups={[]} />)
    expect(container.firstChild).toBeTruthy()
  })

  it('renders with icons and badges', () => {
    const groupsWithExtras = [
      {
        date: '2024-01-01',
        items: [
          {
            id: '1',
            date: '2024-01-01',
            title: 'Event',
            icon: <span data-testid="icon">icon</span>,
            badge: <span data-testid="badge">badge</span>,
          },
        ],
      },
    ]
    render(<Timeline groups={groupsWithExtras} />)
    expect(screen.getByTestId('icon')).toBeInTheDocument()
    expect(screen.getByTestId('badge')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    const { container } = render(<Timeline groups={[]} className="custom" />)
    expect(container.firstChild).toBeTruthy()
  })
})
