import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EmptyState } from '../EmptyState'

describe('EmptyState', () => {
  it('renders default title', () => {
    render(<EmptyState />)
    expect(screen.getByText('暂无数据')).toBeInTheDocument()
  })

  it('renders custom title and description', () => {
    render(<EmptyState title="No items" description="Try adding some" />)
    expect(screen.getByText('No items')).toBeInTheDocument()
    expect(screen.getByText('Try adding some')).toBeInTheDocument()
  })

  it('does not render action button when actionText is not provided', () => {
    render(<EmptyState />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('renders action button and calls onAction', async () => {
    const onAction = vi.fn()
    render(<EmptyState actionText="Add Item" onAction={onAction} />)
    const btn = screen.getByRole('button', { name: 'Add Item' })
    await userEvent.click(btn)
    expect(onAction).toHaveBeenCalledOnce()
  })

  it('renders with different icon types', () => {
    const { rerender } = render(<EmptyState icon="users" />)
    expect(screen.getByText('暂无数据')).toBeInTheDocument()

    rerender(<EmptyState icon="search" />)
    expect(screen.getByText('暂无数据')).toBeInTheDocument()

    rerender(<EmptyState icon="folder" />)
    expect(screen.getByText('暂无数据')).toBeInTheDocument()
  })
})
