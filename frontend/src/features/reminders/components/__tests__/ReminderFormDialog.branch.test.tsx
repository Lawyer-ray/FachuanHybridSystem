/**
 * Branch-focused tests for ReminderFormDialog.tsx
 * Targets uncovered branches: formDataToInput, handleSubmit edit/create modes,
 * onSuccess callbacks, onError callbacks, handleCancel
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { ReminderFormDialog } from '../ReminderFormDialog'
import { toast } from 'sonner'

vi.mock('../../hooks/use-reminder-mutations', () => {
  const mockCreateMutate = vi.fn()
  const mockUpdateMutate = vi.fn()
  return {
    useReminderMutations: () => ({
      createMutation: { mutate: mockCreateMutate, isPending: false },
      updateMutation: { mutate: mockUpdateMutate, isPending: false },
    }),
    __mockCreateMutate: mockCreateMutate,
    __mockUpdateMutate: mockUpdateMutate,
  }
})

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('../ReminderForm', () => ({
  ReminderForm: ({ mode, onSubmit, onCancel, isSubmitting, contractOptions, initialDate }: any) => (
    <div data-testid="reminder-form">
      <span>Form mode: {mode}</span>
      <span>Submitting: {String(isSubmitting)}</span>
      {contractOptions?.length > 0 && <span>Has contracts</span>}
      {initialDate && <span>Has initial date</span>}
      <button onClick={() => onSubmit({
        reminder_type: 'hearing',
        content: 'Test reminder',
        due_at: new Date('2025-06-15T10:00:00Z'),
        contract_id: null,
        case_log_id: null,
        metadata: {},
      })}>Submit</button>
      <button onClick={() => onSubmit({
        reminder_type: 'hearing',
        content: 'Test reminder',
        due_at: new Date('2025-06-15T10:00:00Z'),
        contract_id: 5,
        case_log_id: null,
        metadata: { key: 'value' },
      })}>Submit with contract</button>
      <button onClick={() => onSubmit({
        reminder_type: 'hearing',
        content: 'Test reminder',
        due_at: new Date('2025-06-15T10:00:00Z'),
        contract_id: null,
        case_log_id: 10,
        metadata: undefined,
      })}>Submit with caselog</button>
      <button onClick={onCancel}>Cancel</button>
    </div>
  ),
}))

import { __mockCreateMutate, __mockUpdateMutate } from '../../hooks/use-reminder-mutations'
const mockCreateMutate = __mockCreateMutate as ReturnType<typeof vi.fn>
const mockUpdateMutate = __mockUpdateMutate as ReturnType<typeof vi.fn>

describe('ReminderFormDialog - branch coverage', () => {
  beforeEach(() => vi.clearAllMocks())

  // formDataToInput: contract_id ?? null (branch 0: truthy vs null)
  it('submits create with contract_id', () => {
    render(<ReminderFormDialog open={true} onOpenChange={vi.fn()} mode="create" />)
    fireEvent.click(screen.getByText('Submit with contract'))
    expect(mockCreateMutate).toHaveBeenCalledWith(
      expect.objectContaining({ contract_id: 5 }),
      expect.any(Object),
    )
  })

  // formDataToInput: case_log_id ?? null (branch 1: truthy vs null)
  it('submits create with case_log_id', () => {
    render(<ReminderFormDialog open={true} onOpenChange={vi.fn()} mode="create" />)
    fireEvent.click(screen.getByText('Submit with caselog'))
    expect(mockCreateMutate).toHaveBeenCalledWith(
      expect.objectContaining({ case_log_id: 10 }),
      expect.any(Object),
    )
  })

  // formDataToInput: metadata ?? {} (branch 2: undefined -> {})
  it('submits create with undefined metadata defaulting to {}', () => {
    render(<ReminderFormDialog open={true} onOpenChange={vi.fn()} mode="create" />)
    fireEvent.click(screen.getByText('Submit with caselog'))
    expect(mockCreateMutate).toHaveBeenCalledWith(
      expect.objectContaining({ metadata: {} }),
      expect.any(Object),
    )
  })

  // handleSubmit: isEditMode && reminder branch (branch 5: edit mode with reminder)
  it('submits edit mode with reminder', () => {
    const reminder = { id: 42, reminder_type: 'hearing', content: 'Old' } as any
    render(<ReminderFormDialog open={true} onOpenChange={vi.fn()} mode="edit" reminder={reminder} />)
    fireEvent.click(screen.getByText('Submit'))
    expect(mockUpdateMutate).toHaveBeenCalledWith(
      { id: 42, data: expect.objectContaining({ reminder_type: 'hearing' }) },
      expect.any(Object),
    )
  })

  // handleSubmit: create mode (branch 5[1])
  it('submits create mode', () => {
    render(<ReminderFormDialog open={true} onOpenChange={vi.fn()} mode="create" />)
    fireEvent.click(screen.getByText('Submit'))
    expect(mockCreateMutate).toHaveBeenCalled()
  })

  // handleSubmit: edit mode success callback (branch 6: onSuccess)
  it('shows success toast and closes on edit success', () => {
    const onOpenChange = vi.fn()
    const onSuccess = vi.fn()
    const reminder = { id: 42 } as any
    mockUpdateMutate.mockImplementation((_params: any, opts: any) => {
      opts.onSuccess()
    })
    render(<ReminderFormDialog open={true} onOpenChange={onOpenChange} mode="edit" reminder={reminder} onSuccess={onSuccess} />)
    fireEvent.click(screen.getByText('Submit'))
    expect(toast.success).toHaveBeenCalledWith('提醒更新成功')
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onSuccess).toHaveBeenCalled()
  })

  // handleSubmit: edit mode error callback (branch 7)
  it('shows error toast on edit failure', () => {
    const reminder = { id: 42 } as any
    mockUpdateMutate.mockImplementation((_params: any, opts: any) => {
      opts.onError(new Error('Update failed'))
    })
    render(<ReminderFormDialog open={true} onOpenChange={vi.fn()} mode="edit" reminder={reminder} />)
    fireEvent.click(screen.getByText('Submit'))
    expect(toast.error).toHaveBeenCalledWith('更新失败：Update failed')
  })

  // handleSubmit: create mode success callback (branch 8)
  it('shows success toast and closes on create success', () => {
    const onOpenChange = vi.fn()
    const onSuccess = vi.fn()
    mockCreateMutate.mockImplementation((_data: any, opts: any) => {
      opts.onSuccess()
    })
    render(<ReminderFormDialog open={true} onOpenChange={onOpenChange} mode="create" onSuccess={onSuccess} />)
    fireEvent.click(screen.getByText('Submit'))
    expect(toast.success).toHaveBeenCalledWith('提醒创建成功')
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onSuccess).toHaveBeenCalled()
  })

  // handleSubmit: create mode error callback (branch 8[1])
  it('shows error toast on create failure', () => {
    mockCreateMutate.mockImplementation((_data: any, opts: any) => {
      opts.onError(new Error('Create failed'))
    })
    render(<ReminderFormDialog open={true} onOpenChange={vi.fn()} mode="create" />)
    fireEvent.click(screen.getByText('Submit'))
    expect(toast.error).toHaveBeenCalledWith('创建失败：Create failed')
  })

  // handleSubmit: error without message (branch 7[1])
  it('shows fallback error message when error has no message', () => {
    mockCreateMutate.mockImplementation((_data: any, opts: any) => {
      opts.onError({})
    })
    render(<ReminderFormDialog open={true} onOpenChange={vi.fn()} mode="create" />)
    fireEvent.click(screen.getByText('Submit'))
    expect(toast.error).toHaveBeenCalledWith('创建失败：请稍后重试')
  })

  // handleSubmit: edit error without message (branch 7[1])
  it('shows fallback edit error message', () => {
    const reminder = { id: 1 } as any
    mockUpdateMutate.mockImplementation((_params: any, opts: any) => {
      opts.onError({})
    })
    render(<ReminderFormDialog open={true} onOpenChange={vi.fn()} mode="edit" reminder={reminder} />)
    fireEvent.click(screen.getByText('Submit'))
    expect(toast.error).toHaveBeenCalledWith('更新失败：请稍后重试')
  })

  // handleCancel (fn 7: line 162)
  it('calls onOpenChange(false) on cancel', () => {
    const onOpenChange = vi.fn()
    render(<ReminderFormDialog open={true} onOpenChange={onOpenChange} mode="create" />)
    fireEvent.click(screen.getByText('Cancel'))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  // isSubmitting computed (line 112)
  it('passes isSubmitting to ReminderForm', () => {
    render(<ReminderFormDialog open={true} onOpenChange={vi.fn()} mode="create" />)
    expect(screen.getByText('Submitting: false')).toBeInTheDocument()
  })

  // contractOptions and initialDate passed through
  it('passes contractOptions and initialDate to ReminderForm', () => {
    const options = [{ id: 1, label: 'Contract A' }]
    const date = new Date()
    render(<ReminderFormDialog open={true} onOpenChange={vi.fn()} mode="create" contractOptions={options} initialDate={date} />)
    expect(screen.getByText('Has contracts')).toBeInTheDocument()
    expect(screen.getByText('Has initial date')).toBeInTheDocument()
  })

  // Edit mode title and description
  it('renders edit mode title and description', () => {
    render(<ReminderFormDialog open={true} onOpenChange={vi.fn()} mode="edit" />)
    expect(screen.getByText('编辑提醒')).toBeInTheDocument()
    expect(screen.getByText('修改提醒信息，完成后点击保存')).toBeInTheDocument()
  })

  // Create mode without onSuccess (branch: onSuccess?.())
  it('handles create success without onSuccess callback', () => {
    mockCreateMutate.mockImplementation((_data: any, opts: any) => {
      opts.onSuccess()
    })
    render(<ReminderFormDialog open={true} onOpenChange={vi.fn()} mode="create" />)
    fireEvent.click(screen.getByText('Submit'))
    expect(toast.success).toHaveBeenCalled()
  })

  // Edit mode without onSuccess callback
  it('handles edit success without onSuccess callback', () => {
    const reminder = { id: 1 } as any
    mockUpdateMutate.mockImplementation((_params: any, opts: any) => {
      opts.onSuccess()
    })
    render(<ReminderFormDialog open={true} onOpenChange={vi.fn()} mode="edit" reminder={reminder} />)
    fireEvent.click(screen.getByText('Submit'))
    expect(toast.success).toHaveBeenCalled()
  })

  // edit mode without reminder (guard: isEditMode && reminder)
  it('does not submit in edit mode without reminder', () => {
    render(<ReminderFormDialog open={true} onOpenChange={vi.fn()} mode="edit" />)
    fireEvent.click(screen.getByText('Submit'))
    // Should go to create path since !reminder
    expect(mockCreateMutate).toHaveBeenCalled()
  })

  // formDataToInput: contract_id null (branch 0[1])
  it('submits with null contract_id', () => {
    render(<ReminderFormDialog open={true} onOpenChange={vi.fn()} mode="create" />)
    fireEvent.click(screen.getByText('Submit'))
    expect(mockCreateMutate).toHaveBeenCalledWith(
      expect.objectContaining({ contract_id: null, case_log_id: null }),
      expect.any(Object),
    )
  })
})
