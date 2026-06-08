import { render, screen } from '@testing-library/react'
import { QuoteStatusBadge } from '../QuoteStatusBadge'

describe('QuoteStatusBadge', () => {
  it('renders without crashing for each status', () => {
    const statuses = ['pending', 'running', 'success', 'partial_success', 'failed'] as const
    for (const status of statuses) {
      const { unmount } = render(<QuoteStatusBadge status={status} />)
      unmount()
    }
  })

  it('displays correct label for pending status', () => {
    render(<QuoteStatusBadge status="pending" />)
    expect(screen.getByText('待执行')).toBeInTheDocument()
  })

  it('displays correct label for running status', () => {
    render(<QuoteStatusBadge status="running" />)
    expect(screen.getByText('执行中')).toBeInTheDocument()
  })

  it('displays correct label for success status', () => {
    render(<QuoteStatusBadge status="success" />)
    expect(screen.getByText('成功')).toBeInTheDocument()
  })

  it('displays correct label for partial_success status', () => {
    render(<QuoteStatusBadge status="partial_success" />)
    expect(screen.getByText('部分成功')).toBeInTheDocument()
  })

  it('displays correct label for failed status', () => {
    render(<QuoteStatusBadge status="failed" />)
    expect(screen.getByText('失败')).toBeInTheDocument()
  })

  it('hides dot indicator when showDot is false', () => {
    const { container } = render(<QuoteStatusBadge status="pending" showDot={false} />)
    // When showDot is false, there should be no small dot span inside the badge
    const badge = container.querySelector('[data-slot="badge"]')
    const dotSpans = badge?.querySelectorAll('span[class*="h-1.5"]')
    expect(dotSpans?.length ?? 0).toBe(0)
  })

  it('shows dot indicator by default for non-running status', () => {
    const { container } = render(<QuoteStatusBadge status="success" />)
    const badge = container.querySelector('[data-slot="badge"]')
    const dotSpans = badge?.querySelectorAll('span[class*="h-1.5"]')
    expect((dotSpans?.length ?? 0)).toBeGreaterThan(0)
  })

  it('applies custom className', () => {
    const { container } = render(<QuoteStatusBadge status="pending" className="custom-class" />)
    expect(container.firstChild).toHaveClass('custom-class')
  })

  it('renders loading spinner for running status', () => {
    const { container } = render(<QuoteStatusBadge status="running" />)
    expect(container.querySelector('[class*="animate-spin"]')).toBeInTheDocument()
  })
})
