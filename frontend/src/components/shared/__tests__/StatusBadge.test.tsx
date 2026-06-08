import { render, screen } from '@testing-library/react'
import { StatusBadge } from '../StatusBadge'

describe('StatusBadge', () => {
  it('renders children text', () => {
    render(<StatusBadge variant="active">Active</StatusBadge>)
    expect(screen.getByText('Active')).toBeInTheDocument()
  })

  it('renders with different variants', () => {
    const { rerender } = render(<StatusBadge variant="pending">Pending</StatusBadge>)
    expect(screen.getByText('Pending')).toBeInTheDocument()

    rerender(<StatusBadge variant="error">Error</StatusBadge>)
    expect(screen.getByText('Error')).toBeInTheDocument()

    rerender(<StatusBadge variant="success">Success</StatusBadge>)
    expect(screen.getByText('Success')).toBeInTheDocument()

    rerender(<StatusBadge variant="info">Info</StatusBadge>)
    expect(screen.getByText('Info')).toBeInTheDocument()

    rerender(<StatusBadge variant="purple">Purple</StatusBadge>)
    expect(screen.getByText('Purple')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    render(<StatusBadge variant="active" className="extra-class">Test</StatusBadge>)
    const badge = screen.getByText('Test')
    expect(badge.className).toContain('extra-class')
  })

  it('applies variant-specific styles', () => {
    render(<StatusBadge variant="active">Active</StatusBadge>)
    const badge = screen.getByText('Active')
    expect(badge.className).toContain('rounded-full')
    expect(badge.className).toContain('status-green')
  })
})
