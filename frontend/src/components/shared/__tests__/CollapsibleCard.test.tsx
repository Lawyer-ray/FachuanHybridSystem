import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CollapsibleCard } from '../CollapsibleCard'

describe('CollapsibleCard', () => {
  it('renders title and children', () => {
    render(<CollapsibleCard title="Section"><p>content</p></CollapsibleCard>)
    expect(screen.getByText('Section')).toBeInTheDocument()
    expect(screen.getByText('content')).toBeInTheDocument()
  })

  it('starts expanded by default', () => {
    render(<CollapsibleCard title="Test"><p>visible</p></CollapsibleCard>)
    expect(screen.getByText('visible')).toBeInTheDocument()
  })

  it('starts collapsed when defaultCollapsed is true', () => {
    render(<CollapsibleCard title="Test" defaultCollapsed><p>hidden</p></CollapsibleCard>)
    expect(screen.queryByText('hidden')).not.toBeInTheDocument()
  })

  it('toggles on header click', async () => {
    render(<CollapsibleCard title="Test"><p>toggle me</p></CollapsibleCard>)
    const header = screen.getByText('Test')
    expect(screen.getByText('toggle me')).toBeInTheDocument()

    await userEvent.click(header)
    expect(screen.queryByText('toggle me')).not.toBeInTheDocument()

    await userEvent.click(header)
    expect(screen.getByText('toggle me')).toBeInTheDocument()
  })

  it('renders headerRight content', () => {
    render(
      <CollapsibleCard title="Test" headerRight={<button>Action</button>}>
        <p>content</p>
      </CollapsibleCard>
    )
    expect(screen.getByText('Action')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    const { container } = render(
      <CollapsibleCard title="Test" className="custom"><p>content</p></CollapsibleCard>
    )
    const card = container.firstChild as HTMLElement
    expect(card.className).toContain('custom')
  })
})
