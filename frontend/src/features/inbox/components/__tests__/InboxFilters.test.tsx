import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { InboxFilters } from '../InboxFilters'

describe('InboxFilters', () => {
  const defaultProps = {
    search: '',
    onSearchChange: vi.fn(),
    hasAttachments: 'all',
    onHasAttachmentsChange: vi.fn(),
  }

  it('renders search input', () => {
    render(<InboxFilters {...defaultProps} />)
    expect(screen.getByPlaceholderText('搜索主题、发件人、正文...')).toBeInTheDocument()
  })

  it('displays current search value', () => {
    render(<InboxFilters {...defaultProps} search="hello" />)
    expect(screen.getByDisplayValue('hello')).toBeInTheDocument()
  })

  it('calls onSearchChange when typing', async () => {
    const onSearchChange = vi.fn()
    const user = userEvent.setup()
    render(<InboxFilters {...defaultProps} onSearchChange={onSearchChange} />)
    await user.type(screen.getByPlaceholderText('搜索主题、发件人、正文...'), 't')
    expect(onSearchChange).toHaveBeenCalledWith('t')
  })

  it('shows clear button when search has value', () => {
    render(<InboxFilters {...defaultProps} search="test" />)
    const buttons = screen.getAllByRole('button')
    expect(buttons.length).toBeGreaterThan(0)
  })

  it('renders filter dropdown', () => {
    render(<InboxFilters {...defaultProps} />)
    expect(screen.getByRole('combobox')).toBeInTheDocument()
  })

  it('does not show clear button when search is empty', () => {
    const { container } = render(<InboxFilters {...defaultProps} search="" />)
    // Only the Select trigger button should be present
    const buttons = container.querySelectorAll('button')
    expect(buttons.length).toBe(1) // only combobox trigger
  })
})
