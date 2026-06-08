vi.mock('../../hooks/use-reminders', () => ({
  useReminderTypes: vi.fn().mockReturnValue({ data: undefined }),
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { render, screen } from '@testing-library/react'
import { ReminderForm } from '../ReminderForm'

describe('ReminderForm', () => {
  it('renders form fields in create mode', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} />)
    expect(screen.getByText('提醒类型')).toBeInTheDocument()
    expect(screen.getByText('提醒事项')).toBeInTheDocument()
    expect(screen.getByText('到期时间')).toBeInTheDocument()
  })

  it('renders create button text', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} />)
    expect(screen.getByText('创建')).toBeInTheDocument()
  })

  it('renders save button text in edit mode', () => {
    render(<ReminderForm mode="edit" onSubmit={vi.fn()} />)
    expect(screen.getByText('保存')).toBeInTheDocument()
  })

  it('renders cancel button when onCancel provided', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.getByText('取消')).toBeInTheDocument()
  })

  it('shows loading text when submitting', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} isSubmitting />)
    expect(screen.getByText('创建中...')).toBeInTheDocument()
  })
})
