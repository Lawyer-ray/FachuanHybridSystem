import { render, screen } from '@testing-library/react'
import { DetailCard } from '../DetailCard'

describe('DetailCard', () => {
  it('renders title', () => {
    render(<DetailCard title="Basic Info"><div>content</div></DetailCard>)
    expect(screen.getByText('Basic Info')).toBeInTheDocument()
  })

  it('renders children', () => {
    render(<DetailCard title="Test"><p>child content</p></DetailCard>)
    expect(screen.getByText('child content')).toBeInTheDocument()
  })

  it('renders extra content when provided', () => {
    render(
      <DetailCard title="Test" extra={<button>Edit</button>}>
        <div>content</div>
      </DetailCard>
    )
    expect(screen.getByText('Edit')).toBeInTheDocument()
    expect(screen.getByText('Test')).toBeInTheDocument()
  })

  it('does not render extra when not provided', () => {
    const { container } = render(
      <DetailCard title="Test"><div>content</div></DetailCard>
    )
    const headings = container.querySelectorAll('h3')
    expect(headings).toHaveLength(1)
  })
})
