import { render, screen } from '@testing-library/react'
import { DetailCardGrid } from '../DetailCardGrid'

describe('DetailCardGrid', () => {
  it('renders title', () => {
    render(<DetailCardGrid title="Basic Info" items={[]} />)
    expect(screen.getByText('Basic Info')).toBeInTheDocument()
  })

  it('renders items with labels and values', () => {
    const items = [
      { label: 'Name', value: 'John' },
      { label: 'Age', value: '30' },
    ]
    render(<DetailCardGrid title="Info" items={items} />)
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByText('John')).toBeInTheDocument()
    expect(screen.getByText('Age')).toBeInTheDocument()
    expect(screen.getByText('30')).toBeInTheDocument()
  })

  it('renders dash for undefined values', () => {
    const items = [{ label: 'Empty' }]
    render(<DetailCardGrid title="Test" items={items} />)
    expect(screen.getByText('-')).toBeInTheDocument()
  })

  it('renders headerRight content', () => {
    render(
      <DetailCardGrid title="Test" items={[]} headerRight={<button>Edit</button>} />
    )
    expect(screen.getByText('Edit')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    const { container } = render(
      <DetailCardGrid title="Test" items={[]} className="custom-class" />
    )
    const card = container.firstChild as HTMLElement
    expect(card.className).toContain('custom-class')
  })

  it('passes columns to InfoGrid', () => {
    const items = [{ label: 'A', value: '1' }]
    render(<DetailCardGrid title="Test" items={items} columns={3} />)
    // Just verify it renders without error
    expect(screen.getByText('A')).toBeInTheDocument()
  })
})
