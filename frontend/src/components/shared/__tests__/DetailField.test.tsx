import { render, screen } from '@testing-library/react'
import { DetailField } from '../DetailField'

describe('DetailField', () => {
  it('renders label and value', () => {
    render(<DetailField label="Name" value="John" />)
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByText('John')).toBeInTheDocument()
  })

  it('renders dash when value is falsy', () => {
    render(<DetailField label="Name" value="" />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('renders dash when value is null', () => {
    render(<DetailField label="Name" value={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('applies mono class when mono is true', () => {
    const { container } = render(<DetailField label="ID" value="12345" mono />)
    const allDivs = container.querySelectorAll('div')
    // Structure: container > root-div > label-div + value-div
    // querySelectorAll returns [root-div, label-div, value-div]
    const valueEl = allDivs[2]
    expect(valueEl.className).toContain('font-mono')
  })

  it('does not apply mono class by default', () => {
    const { container } = render(<DetailField label="Name" value="John" />)
    const allDivs = container.querySelectorAll('div')
    const valueEl = allDivs[2]
    expect(valueEl.className).not.toContain('font-mono')
  })

  it('renders ReactNode value', () => {
    render(<DetailField label="Status" value={<span>Active</span>} />)
    expect(screen.getByText('Active')).toBeInTheDocument()
  })
})
