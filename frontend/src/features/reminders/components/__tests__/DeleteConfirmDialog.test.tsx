import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DeleteConfirmDialog } from '../DeleteConfirmDialog'

const mockMutate = vi.fn()

vi.mock('@/features/reminders/hooks/use-reminder-mutations', () => ({
  useReminderMutations: () => ({
    deleteMutation: {
      mutate: mockMutate,
      isPending: false,
    },
  }),
}))

describe('DeleteConfirmDialog', () => {
  const baseReminder = {
    id: 1,
    content: 'Court hearing tomorrow',
    reminder_type: 'hearing',
    reminder_type_label: '开庭',
    due_at: '2026-06-20T09:00:00Z',
    priority: 'high',
    is_completed: false,
    contract: null,
    case: 1,
    case_log: null,
    metadata: {},
    created_at: '2026-06-15T10:00:00Z',
  } as any

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders nothing when reminder is null', () => {
    const { container } = render(
      <DeleteConfirmDialog open={true} onOpenChange={vi.fn()} reminder={null} />,
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders the dialog when open with a reminder', () => {
    render(
      <DeleteConfirmDialog open={true} onOpenChange={vi.fn()} reminder={baseReminder} />,
    )
    expect(screen.getByText('确认删除提醒')).toBeInTheDocument()
    expect(screen.getByText(/Court hearing tomorrow/)).toBeInTheDocument()
  })

  it('renders confirm and cancel buttons', () => {
    render(
      <DeleteConfirmDialog open={true} onOpenChange={vi.fn()} reminder={baseReminder} />,
    )
    expect(screen.getByRole('button', { name: '取消' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '确认删除' })).toBeInTheDocument()
  })

  it('calls deleteMutation on confirm', async () => {
    const onSuccess = vi.fn()
    const onOpenChange = vi.fn()
    mockMutate.mockImplementation((_id: number, opts: { onSuccess: () => void }) => {
      opts.onSuccess()
    })

    const user = userEvent.setup()
    render(
      <DeleteConfirmDialog
        open={true}
        onOpenChange={onOpenChange}
        reminder={baseReminder}
        onSuccess={onSuccess}
      />,
    )
    await user.click(screen.getByRole('button', { name: '确认删除' }))
    expect(mockMutate).toHaveBeenCalledWith(1, expect.any(Object))
  })

  it('calls onOpenChange(false) when cancel is clicked', async () => {
    const onOpenChange = vi.fn()
    const user = userEvent.setup()
    render(
      <DeleteConfirmDialog open={true} onOpenChange={onOpenChange} reminder={baseReminder} />,
    )
    await user.click(screen.getByRole('button', { name: '取消' }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})
