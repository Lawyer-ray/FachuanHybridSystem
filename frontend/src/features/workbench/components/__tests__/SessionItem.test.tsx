import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SessionItem } from '../SessionItem'

vi.mock('@/lib/file-utils', () => ({
  formatFileSize: (bytes: number) => `${bytes}B`,
}))

describe('SessionItem', () => {
  const baseSession = {
    id: 1,
    title: 'Test Session',
    last_message_preview: 'Hello world',
    message_count: 5,
    storage_bytes: 1024,
  }

  it('renders session title', () => {
    render(
      <SessionItem
        session={baseSession}
        isActive={false}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.getByText('Test Session')).toBeInTheDocument()
  })

  it('renders last message preview', () => {
    render(
      <SessionItem
        session={baseSession}
        isActive={false}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.getByText('Hello world')).toBeInTheDocument()
  })

  it('renders message count and storage', () => {
    render(
      <SessionItem
        session={baseSession}
        isActive={false}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.getByText(/5 条消息/)).toBeInTheDocument()
  })

  it('shows "新会话" when title is empty', () => {
    render(
      <SessionItem
        session={{ ...baseSession, title: '' }}
        isActive={false}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.getByText('新会话')).toBeInTheDocument()
  })

  it('calls onSelect when clicking the item', async () => {
    const onSelect = vi.fn()
    const user = userEvent.setup()
    render(
      <SessionItem
        session={baseSession}
        isActive={false}
        onSelect={onSelect}
        onDelete={vi.fn()}
      />,
    )
    await user.click(screen.getByText('Test Session'))
    expect(onSelect).toHaveBeenCalledTimes(1)
  })

  it('calls onDelete when delete button is clicked', async () => {
    const onDelete = vi.fn()
    const user = userEvent.setup()
    render(
      <SessionItem
        session={baseSession}
        isActive={false}
        onSelect={vi.fn()}
        onDelete={onDelete}
      />,
    )
    const deleteButton = screen.getByRole('button')
    await user.click(deleteButton)
    expect(onDelete).toHaveBeenCalledTimes(1)
  })

  it('applies active class when isActive is true', () => {
    const { container } = render(
      <SessionItem
        session={baseSession}
        isActive={true}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(container.firstChild).toHaveClass('bg-accent')
  })

  it('hides message count when not provided', () => {
    render(
      <SessionItem
        session={{ ...baseSession, message_count: undefined, storage_bytes: undefined }}
        isActive={false}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
      />,
    )
    expect(screen.queryByText(/条消息/)).not.toBeInTheDocument()
  })
})
