vi.mock('../../hooks/use-reminder-mutations', () => ({
  useReminderMutations: () => ({
    createMutation: { mutate: vi.fn(), isPending: false },
    updateMutation: { mutate: vi.fn(), isPending: false },
  }),
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('../ReminderForm', () => ({
  ReminderForm: ({ mode }: any) => (
    <div data-testid="reminder-form">Form mode: {mode}</div>
  ),
}))

import { render, screen } from '@testing-library/react'
import { ReminderFormDialog } from '../ReminderFormDialog'

describe('ReminderFormDialog', () => {
  it('renders create mode title', () => {
    render(<ReminderFormDialog open onOpenChange={vi.fn()} mode="create" />)
    expect(screen.getByText('新建提醒')).toBeInTheDocument()
  })

  it('renders edit mode title', () => {
    render(<ReminderFormDialog open onOpenChange={vi.fn()} mode="edit" />)
    expect(screen.getByText('编辑提醒')).toBeInTheDocument()
  })

  it('renders create description', () => {
    render(<ReminderFormDialog open onOpenChange={vi.fn()} mode="create" />)
    expect(screen.getByText('填写提醒信息，创建新的重要日期提醒')).toBeInTheDocument()
  })

  it('renders ReminderForm child', () => {
    render(<ReminderFormDialog open onOpenChange={vi.fn()} mode="create" />)
    expect(screen.getByTestId('reminder-form')).toBeInTheDocument()
  })
})
