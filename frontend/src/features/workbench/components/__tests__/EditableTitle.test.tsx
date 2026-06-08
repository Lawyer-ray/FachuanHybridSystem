import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { EditableTitle } from '../EditableTitle'

describe('EditableTitle', () => {
  it('renders title text when not editable', () => {
    render(<EditableTitle title="My Title" editable={false} onSave={vi.fn()} />)
    expect(screen.getByText('My Title')).toBeInTheDocument()
  })

  it('renders title text when editable but not editing', () => {
    render(<EditableTitle title="My Title" editable={true} onSave={vi.fn()} />)
    expect(screen.getByText('My Title')).toBeInTheDocument()
  })

  it('shows edit button on hover when editable', () => {
    const { container } = render(<EditableTitle title="My Title" editable={true} onSave={vi.fn()} />)
    // The pencil icon button should be in the DOM (hidden by CSS)
    expect(container.querySelector('button')).toBeInTheDocument()
  })

  it('enters editing mode when clicking edit button', async () => {
    const user = userEvent.setup()
    render(<EditableTitle title="My Title" editable={true} onSave={vi.fn()} />)
    const button = screen.getByRole('button')
    await user.click(button)
    expect(screen.getByDisplayValue('My Title')).toBeInTheDocument()
  })

  it('saves on blur after editing', async () => {
    const onSave = vi.fn()
    const user = userEvent.setup()
    render(<EditableTitle title="Old Title" editable={true} onSave={onSave} />)
    await user.click(screen.getByRole('button'))
    const input = screen.getByDisplayValue('Old Title')
    await user.clear(input)
    await user.type(input, 'New Title')
    await user.tab() // blur
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith('New Title')
    })
  })

  it('cancels edit on Escape key', async () => {
    const onSave = vi.fn()
    const user = userEvent.setup()
    render(<EditableTitle title="Original" editable={true} onSave={onSave} />)
    await user.click(screen.getByRole('button'))
    const input = screen.getByDisplayValue('Original')
    await user.clear(input)
    await user.type(input, 'Changed')
    await user.keyboard('{Escape}')
    expect(onSave).not.toHaveBeenCalled()
    // Should show original title again
    expect(screen.getByText('Original')).toBeInTheDocument()
  })

  it('saves on Enter key', async () => {
    const onSave = vi.fn()
    const user = userEvent.setup()
    render(<EditableTitle title="Old" editable={true} onSave={onSave} />)
    await user.click(screen.getByRole('button'))
    const input = screen.getByDisplayValue('Old')
    await user.clear(input)
    await user.type(input, 'New')
    await user.keyboard('{Enter}')
    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith('New')
    })
  })

  it('does not save if value is empty', async () => {
    const onSave = vi.fn()
    const user = userEvent.setup()
    render(<EditableTitle title="Title" editable={true} onSave={onSave} />)
    await user.click(screen.getByRole('button'))
    const input = screen.getByDisplayValue('Title')
    await user.clear(input)
    await user.tab()
    // Empty value should not trigger save
    expect(onSave).not.toHaveBeenCalled()
  })
})
