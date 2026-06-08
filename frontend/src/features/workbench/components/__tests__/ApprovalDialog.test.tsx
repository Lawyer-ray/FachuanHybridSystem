import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ApprovalDialog } from '../ApprovalDialog'

describe('ApprovalDialog', () => {
  const baseApproval = {
    approvalId: 'test-123',
    toolName: 'create_case',
    toolArgs: { name: 'Test Case', client_id: 1 },
  }

  it('renders the approval dialog', () => {
    render(<ApprovalDialog approval={baseApproval} onRespond={vi.fn()} />)
    expect(screen.getByText('需要确认')).toBeInTheDocument()
  })

  it('displays the tool name', () => {
    render(<ApprovalDialog approval={baseApproval} onRespond={vi.fn()} />)
    expect(screen.getByText('create_case')).toBeInTheDocument()
  })

  it('displays tool args as JSON', () => {
    render(<ApprovalDialog approval={baseApproval} onRespond={vi.fn()} />)
    expect(screen.getByText(/Test Case/)).toBeInTheDocument()
  })

  it('renders approve and reject buttons', () => {
    render(<ApprovalDialog approval={baseApproval} onRespond={vi.fn()} />)
    expect(screen.getByRole('button', { name: '批准' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '拒绝' })).toBeInTheDocument()
  })

  it('calls onRespond(true) when approve is clicked', async () => {
    const onRespond = vi.fn()
    const user = userEvent.setup()
    render(<ApprovalDialog approval={baseApproval} onRespond={onRespond} />)
    await user.click(screen.getByRole('button', { name: '批准' }))
    expect(onRespond).toHaveBeenCalledWith(true)
  })

  it('calls onRespond(false) when reject is clicked', async () => {
    const onRespond = vi.fn()
    const user = userEvent.setup()
    render(<ApprovalDialog approval={baseApproval} onRespond={onRespond} />)
    await user.click(screen.getByRole('button', { name: '拒绝' }))
    expect(onRespond).toHaveBeenCalledWith(false)
  })

  it('does not show JSON when toolArgs is empty', () => {
    const emptyArgsApproval = { ...baseApproval, toolArgs: {} }
    render(<ApprovalDialog approval={emptyArgsApproval} onRespond={vi.fn()} />)
    expect(screen.queryByText(/Test Case/)).not.toBeInTheDocument()
  })

  it('shows warning icon', () => {
    const { container } = render(<ApprovalDialog approval={baseApproval} onRespond={vi.fn()} />)
    expect(container.querySelector('svg')).toBeInTheDocument()
  })
})
