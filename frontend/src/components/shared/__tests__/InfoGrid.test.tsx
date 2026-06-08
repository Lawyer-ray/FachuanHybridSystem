import { render, screen } from '@testing-library/react'
import { InfoGrid } from '../InfoGrid'

describe('InfoGrid', () => {
  it('renders items with labels and values', () => {
    const items = [
      { label: 'Name', value: 'John' },
      { label: 'Age', value: '30' },
    ]
    render(<InfoGrid items={items} />)
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByText('John')).toBeInTheDocument()
    expect(screen.getByText('Age')).toBeInTheDocument()
    expect(screen.getByText('30')).toBeInTheDocument()
  })

  it('renders dash for null values', () => {
    const items = [{ label: 'Empty', value: null }]
    render(<InfoGrid items={items} />)
    expect(screen.getByText('Empty')).toBeInTheDocument()
    expect(screen.getByText('-')).toBeInTheDocument()
  })

  it('applies 2-column grid by default', () => {
    const { container } = render(<InfoGrid items={[{ label: 'A', value: '1' }]} />)
    const grid = container.firstChild as HTMLElement
    expect(grid.className).toContain('grid-cols-1')
    expect(grid.className).toContain('md:grid-cols-2')
  })

  it('applies 1-column grid', () => {
    const { container } = render(<InfoGrid items={[{ label: 'A', value: '1' }]} columns={1} />)
    const grid = container.firstChild as HTMLElement
    expect(grid.className).toContain('grid-cols-1')
    expect(grid.className).not.toContain('md:grid-cols-2')
  })

  it('applies 3-column grid', () => {
    const { container } = render(<InfoGrid items={[{ label: 'A', value: '1' }]} columns={3} />)
    const grid = container.firstChild as HTMLElement
    expect(grid.className).toContain('lg:grid-cols-3')
  })

  it('applies custom className', () => {
    const { container } = render(<InfoGrid items={[]} className="custom-class" />)
    const grid = container.firstChild as HTMLElement
    expect(grid.className).toContain('custom-class')
  })
})
