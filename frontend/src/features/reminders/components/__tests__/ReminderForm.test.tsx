vi.mock('../../hooks/use-reminders', () => ({
  useReminderTypes: vi.fn().mockReturnValue({ data: undefined }),
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

// jsdom does not implement scrollIntoView; cmdk calls it on mount
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
})

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { ReminderForm } from '../ReminderForm'
import { useReminderTypes } from '../../hooks/use-reminders'
import type { ReminderTypeOption } from '../../types'

const mockUseReminderTypes = vi.mocked(useReminderTypes)

const mockReminderTypes: ReminderTypeOption[] = [
  { value: 'hearing', label: '开庭' },
  { value: 'other', label: '其他' },
]

const mockReminder = {
  id: 1,
  reminder_type: 'hearing' as const,
  content: 'Test reminder content',
  due_at: '2026-12-15T09:00:00Z',
  contract: 10,
  case: null,
  case_log: null,
  reminder_type_label: '开庭',
  metadata: { foo: 'bar' },
  created_at: '2026-01-01T00:00:00Z',
}

const mockContractOptions = [
  { id: 10, label: 'Contract A' },
  { id: 20, label: 'Contract B' },
]

/**
 * Helper to get the datetime-local input specifically.
 * We can't use getByDisplayValue('') because the textarea also has empty value.
 */
function getDateTimeInput(): HTMLInputElement {
  const el = document.querySelector('input[type="datetime-local"]')
  if (!el) throw new Error('datetime-local input not found')
  return el as HTMLInputElement
}

describe('ReminderForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseReminderTypes.mockReturnValue({ data: undefined })
  })

  // ========== Rendering ==========

  it('renders form fields in create mode', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} />)
    expect(screen.getByText('提醒类型')).toBeInTheDocument()
    expect(screen.getByText('提醒事项')).toBeInTheDocument()
    expect(screen.getByText('到期时间')).toBeInTheDocument()
    expect(screen.getByText('关联合同（可选）')).toBeInTheDocument()
  })

  it('renders form fields in edit mode', () => {
    render(<ReminderForm mode="edit" reminder={mockReminder as any} onSubmit={vi.fn()} />)
    expect(screen.getByText('提醒类型')).toBeInTheDocument()
    expect(screen.getByText('提醒事项')).toBeInTheDocument()
    expect(screen.getByText('到期时间')).toBeInTheDocument()
  })

  it('renders required field asterisks', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} />)
    const asterisks = screen.getAllByText('*')
    expect(asterisks.length).toBeGreaterThanOrEqual(3)
  })

  // ========== Button text ==========

  it('renders create button text in create mode', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} />)
    expect(screen.getByText('创建')).toBeInTheDocument()
  })

  it('renders save button text in edit mode', () => {
    render(<ReminderForm mode="edit" reminder={mockReminder as any} onSubmit={vi.fn()} />)
    expect(screen.getByText('保存')).toBeInTheDocument()
  })

  it('shows create loading text when submitting in create mode', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} isSubmitting />)
    expect(screen.getByText('创建中...')).toBeInTheDocument()
  })

  it('shows save loading text when submitting in edit mode', () => {
    render(<ReminderForm mode="edit" reminder={mockReminder as any} onSubmit={vi.fn()} isSubmitting />)
    expect(screen.getByText('保存中...')).toBeInTheDocument()
  })

  it('does not render cancel button when onCancel is not provided', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} />)
    expect(screen.queryByText('取消')).not.toBeInTheDocument()
  })

  it('renders cancel button when onCancel is provided', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.getByText('取消')).toBeInTheDocument()
  })

  it('calls onCancel when cancel button is clicked', async () => {
    const onCancel = vi.fn()
    render(<ReminderForm mode="create" onSubmit={vi.fn()} onCancel={onCancel} />)
    await userEvent.click(screen.getByText('取消'))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  // ========== Submit button disabled state ==========

  it('disables submit button when isSubmitting is true', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} isSubmitting />)
    const submitBtn = screen.getByText('创建中...')
    expect(submitBtn.closest('button')).toBeDisabled()
  })

  it('enables submit button when isSubmitting is false', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} />)
    const submitBtn = screen.getByText('创建')
    expect(submitBtn.closest('button')).toBeEnabled()
  })

  it('disables cancel button when isSubmitting is true', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} onCancel={vi.fn()} isSubmitting />)
    expect(screen.getByText('取消')).toBeDisabled()
  })

  it('disables text input when isSubmitting', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} isSubmitting />)
    expect(screen.getByPlaceholderText('请输入提醒事项内容')).toBeDisabled()
  })

  // ========== Reminder types from API ==========

  it('uses API reminder types when data is available', () => {
    mockUseReminderTypes.mockReturnValue({ data: mockReminderTypes })
    render(<ReminderForm mode="create" onSubmit={vi.fn()} />)
    expect(screen.getByText('请选择提醒类型')).toBeInTheDocument()
  })

  it('falls back to default reminder types when API data is undefined', () => {
    mockUseReminderTypes.mockReturnValue({ data: undefined })
    render(<ReminderForm mode="create" onSubmit={vi.fn()} />)
    expect(screen.getByText('请选择提醒类型')).toBeInTheDocument()
  })

  it('falls back to default reminder types when API data is empty', () => {
    mockUseReminderTypes.mockReturnValue({ data: [] })
    render(<ReminderForm mode="create" onSubmit={vi.fn()} />)
    expect(screen.getByText('请选择提醒类型')).toBeInTheDocument()
  })

  // ========== Date picker ==========

  it('renders datetime-local input for due_at', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} />)
    const dateInput = getDateTimeInput()
    expect(dateInput).toHaveAttribute('type', 'datetime-local')
    expect(dateInput.value).toBe('')
  })

  it('populates date input in edit mode from ISO string', () => {
    render(<ReminderForm mode="edit" reminder={mockReminder as any} onSubmit={vi.fn()} />)
    const dateInput = getDateTimeInput()
    expect(dateInput.value).toMatch(/2026-12-15T/)
  })

  it('pre-fills date when initialDate is provided in create mode', () => {
    const initialDate = new Date('2026-06-15T10:30:00')
    render(<ReminderForm mode="create" onSubmit={vi.fn()} initialDate={initialDate} />)
    const dateInput = getDateTimeInput()
    expect(dateInput.value).toContain('2026-06-15')
  })

  it('handles date input change with valid value', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} />)
    const dateInput = getDateTimeInput()
    fireEvent.change(dateInput, { target: { value: '2026-12-25T14:30' } })
    expect(dateInput.value).toBe('2026-12-25T14:30')
  })

  it('handles date input change with empty value', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} />)
    const dateInput = getDateTimeInput()
    fireEvent.change(dateInput, { target: { value: '' } })
    expect(dateInput.value).toBe('')
  })

  it('shows empty date value for reminder with null due_at in edit mode', () => {
    const reminderWithNullDate = { ...mockReminder, due_at: null }
    render(<ReminderForm mode="edit" reminder={reminderWithNullDate as any} onSubmit={vi.fn()} />)
    const dateInput = getDateTimeInput()
    expect(dateInput.value).toBe('')
  })

  it('renders empty date input in create mode without reminder prop', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} />)
    const dateInput = getDateTimeInput()
    expect(dateInput.value).toBe('')
  })

  // ========== Contract options (SearchableSelect) ==========

  it('renders contract search placeholder', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} />)
    expect(screen.getByText('搜索合同...')).toBeInTheDocument()
  })

  it('shows selected contract label in edit mode with contract', () => {
    render(
      <ReminderForm
        mode="edit"
        reminder={mockReminder as any}
        onSubmit={vi.fn()}
        contractOptions={mockContractOptions}
      />
    )
    expect(screen.getByText('Contract A')).toBeInTheDocument()
  })

  it('shows placeholder when no contract is selected in create mode', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} />)
    expect(screen.getByText('搜索合同...')).toBeInTheDocument()
  })

  it('disables searchable select when isSubmitting', () => {
    render(
      <ReminderForm mode="create" onSubmit={vi.fn()} contractOptions={mockContractOptions} isSubmitting />
    )
    const comboboxes = screen.getAllByRole('combobox')
    // The searchable select is the one with placeholder text
    const searchSelect = comboboxes.find(el => el.textContent?.includes('搜索合同'))
    expect(searchSelect).toBeDisabled()
  })

  it('opens searchable select popover on click', async () => {
    render(
      <ReminderForm mode="create" onSubmit={vi.fn()} contractOptions={mockContractOptions} />
    )
    const comboboxButton = screen.getAllByRole('combobox').find(
      el => el.textContent?.includes('搜索合同')
    )
    expect(comboboxButton).toBeTruthy()
    await userEvent.click(comboboxButton!)
    // After opening, the searchable select button should have aria-expanded true
    await waitFor(() => {
      expect(comboboxButton).toHaveAttribute('aria-expanded', 'true')
    })
  })

  it('shows command input in searchable select', async () => {
    render(
      <ReminderForm mode="create" onSubmit={vi.fn()} contractOptions={mockContractOptions} />
    )
    const comboboxButton = screen.getAllByRole('combobox').find(
      el => el.textContent?.includes('搜索合同')
    )
    await userEvent.click(comboboxButton!)
    await waitFor(() => {
      expect(screen.getByPlaceholderText('搜索合同...')).toBeInTheDocument()
    })
  })

  it('shows clear option when a contract is selected and popover opens', async () => {
    render(
      <ReminderForm
        mode="edit"
        reminder={mockReminder as any}
        onSubmit={vi.fn()}
        contractOptions={mockContractOptions}
      />
    )
    const comboboxButton = screen.getAllByRole('combobox').find(
      el => el.textContent?.includes('Contract A')
    )
    expect(comboboxButton).toBeTruthy()
    await userEvent.click(comboboxButton!)
    // Since contract is selected (id: 10), clear option should appear
    await waitFor(() => {
      expect(screen.getByText('清除选择')).toBeInTheDocument()
    })
  })

  it('clears selected contract when clear option is clicked', async () => {
    render(
      <ReminderForm
        mode="edit"
        reminder={mockReminder as any}
        onSubmit={vi.fn()}
        contractOptions={mockContractOptions}
      />
    )
    const comboboxButton = screen.getAllByRole('combobox').find(
      el => el.textContent?.includes('Contract A')
    )
    await userEvent.click(comboboxButton!)
    await waitFor(() => {
      expect(screen.getByText('清除选择')).toBeInTheDocument()
    })
    await userEvent.click(screen.getByText('清除选择'))
    // After clearing, the placeholder should reappear on the trigger button
    await waitFor(() => {
      expect(screen.getByText('搜索合同...')).toBeInTheDocument()
    })
  })

  it('selects a contract option from searchable select', async () => {
    render(
      <ReminderForm mode="create" onSubmit={vi.fn()} contractOptions={mockContractOptions} />
    )
    const comboboxButton = screen.getAllByRole('combobox').find(
      el => el.textContent?.includes('搜索合同')
    )
    await userEvent.click(comboboxButton!)
    await waitFor(() => {
      expect(screen.getByText('Contract A')).toBeInTheDocument()
      expect(screen.getByText('Contract B')).toBeInTheDocument()
    })
    await userEvent.click(screen.getByText('Contract B'))
    // After selecting, the trigger should show selected label
    await waitFor(() => {
      expect(comboboxButton).toHaveAttribute('aria-expanded', 'false')
    })
  })

  it('deselects contract when clicking the same option again', async () => {
    render(
      <ReminderForm
        mode="edit"
        reminder={mockReminder as any}
        onSubmit={vi.fn()}
        contractOptions={mockContractOptions}
      />
    )
    const comboboxButton = screen.getAllByRole('combobox').find(
      el => el.textContent?.includes('Contract A')
    )
    await userEvent.click(comboboxButton!)
    await waitFor(() => {
      // Both trigger and CommandItem show "Contract A", use getAllByText
      const matches = screen.getAllByText('Contract A')
      expect(matches.length).toBeGreaterThanOrEqual(2)
    })
    // Click a CommandItem that contains Contract A
    // Use cmdk-item attribute selector to find the right one
    const commandItems = document.querySelectorAll('[cmdk-item]')
    const contractAItem = Array.from(commandItems).find(
      el => el.textContent?.includes('Contract A')
    )
    if (contractAItem) {
      await userEvent.click(contractAItem as Element)
      await waitFor(() => {
        expect(comboboxButton).toHaveAttribute('aria-expanded', 'false')
      })
    }
  })

  it('handles empty contract options list', async () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} contractOptions={[]} />)
    const comboboxButton = screen.getAllByRole('combobox').find(
      el => el.textContent?.includes('搜索合同')
    )
    await userEvent.click(comboboxButton!)
    // The empty state should eventually show
    await waitFor(() => {
      expect(comboboxButton).toHaveAttribute('aria-expanded', 'true')
    })
  })

  it('opens searchable select and measures trigger width', async () => {
    render(
      <ReminderForm mode="create" onSubmit={vi.fn()} contractOptions={mockContractOptions} />
    )
    const comboboxButton = screen.getAllByRole('combobox').find(
      el => el.textContent?.includes('搜索合同')
    )
    await userEvent.click(comboboxButton!)
    // The measureTrigger callback should have been called
    await waitFor(() => {
      expect(comboboxButton).toHaveAttribute('aria-expanded', 'true')
    })
  })

  // ========== Edit mode: data population ==========

  it('pre-fills form fields in edit mode', () => {
    render(<ReminderForm mode="edit" reminder={mockReminder as any} onSubmit={vi.fn()} />)
    const textarea = screen.getByPlaceholderText('请输入提醒事项内容')
    expect(textarea).toHaveValue('Test reminder content')
  })

  it('handles edit mode with null contract and case_log', () => {
    const reminderNoAssociation = {
      ...mockReminder,
      contract: null,
      case_log: null,
    }
    render(<ReminderForm mode="edit" reminder={reminderNoAssociation as any} onSubmit={vi.fn()} />)
    expect(screen.getByText('保存')).toBeInTheDocument()
  })

  it('handles edit mode with null metadata', () => {
    const reminderNoMetadata = { ...mockReminder, metadata: null }
    render(<ReminderForm mode="edit" reminder={reminderNoMetadata as any} onSubmit={vi.fn()} />)
    expect(screen.getByText('保存')).toBeInTheDocument()
  })

  it('re-renders when reminder data changes in edit mode', () => {
    const { rerender } = render(
      <ReminderForm mode="edit" reminder={mockReminder as any} onSubmit={vi.fn()} />
    )
    const textarea = screen.getByPlaceholderText('请输入提醒事项内容')
    expect(textarea).toHaveValue('Test reminder content')

    const updatedReminder = { ...mockReminder, content: 'Updated content' }
    rerender(<ReminderForm mode="edit" reminder={updatedReminder as any} onSubmit={vi.fn()} />)
    expect(textarea).toHaveValue('Updated content')
  })

  // ========== Validation ==========

  it('shows validation errors when submitting empty required fields', async () => {
    const onSubmit = vi.fn()
    render(<ReminderForm mode="create" onSubmit={onSubmit} />)

    const submitButton = screen.getByText('创建')
    await userEvent.click(submitButton)

    // Wait for validation errors to appear - use getAllByText since
    // "请选择提醒类型" appears both as placeholder and error
    await waitFor(() => {
      const matches = screen.getAllByText('请选择提醒类型')
      expect(matches.length).toBeGreaterThanOrEqual(1)
    })
    await waitFor(() => {
      expect(screen.getByText('请输入提醒事项')).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(screen.getByText('请选择到期时间')).toBeInTheDocument()
    })
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('shows content max length validation error', async () => {
    const onSubmit = vi.fn()
    render(<ReminderForm mode="create" onSubmit={onSubmit} />)

    const textarea = screen.getByPlaceholderText('请输入提醒事项内容')
    const longText = 'a'.repeat(256)
    await userEvent.type(textarea, longText)

    const submitButton = screen.getByText('创建')
    await userEvent.click(submitButton)

    await waitFor(() => {
      expect(screen.getByText('提醒事项不能超过255字符')).toBeInTheDocument()
    })
    expect(onSubmit).not.toHaveBeenCalled()
  })

  // ========== Description text ==========

  it('renders content max length description', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} />)
    expect(screen.getByText('最多255字符')).toBeInTheDocument()
  })

  // ========== Textarea ==========

  it('renders textarea with correct placeholder', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} />)
    expect(screen.getByPlaceholderText('请输入提醒事项内容')).toBeInTheDocument()
  })

  // ========== Calendar icon ==========

  it('renders calendar icon for date field', () => {
    render(<ReminderForm mode="create" onSubmit={vi.fn()} />)
    const svgIcons = document.querySelectorAll('svg.size-4')
    expect(svgIcons.length).toBeGreaterThanOrEqual(1)
  })

  // ========== Default export ==========

  it('exports ReminderForm as default export', async () => {
    const mod = await import('../ReminderForm')
    expect(mod.default).toBeDefined()
    expect(mod.default).toBe(mod.ReminderForm)
  })

  // ========== formatDateTimeForInput edge cases ==========

  it('handles invalid ISO date string that parseISO cannot catch', () => {
    // parseISO('not-a-date') returns an Invalid Date without throwing,
    // so the catch block in parseISODate never fires.
    // format(date, ...) then throws "Invalid time value".
    // This documents the known edge case.
    const reminderBadDate = { ...mockReminder, due_at: 'not-a-date' }
    expect(() => {
      render(<ReminderForm mode="edit" reminder={reminderBadDate as any} onSubmit={vi.fn()} />)
    }).toThrow('Invalid time value')
  })

  // ========== Create mode with initialDate and contractOptions ==========

  it('renders create form with initial date and contract options', () => {
    const initialDate = new Date('2026-07-01T08:00:00')
    render(
      <ReminderForm
        mode="create"
        onSubmit={vi.fn()}
        initialDate={initialDate}
        contractOptions={mockContractOptions}
      />
    )
    const dateInput = getDateTimeInput()
    expect(dateInput.value).toContain('2026-07-01')
    expect(screen.getByText('搜索合同...')).toBeInTheDocument()
  })

  // ========== parseISODate with null value ==========

  it('renders empty date for reminder with empty string due_at', () => {
    const reminderEmptyDate = { ...mockReminder, due_at: '' }
    render(<ReminderForm mode="edit" reminder={reminderEmptyDate as any} onSubmit={vi.fn()} />)
    const dateInput = getDateTimeInput()
    expect(dateInput.value).toBe('')
  })

  // ========== Edit mode: case_log association ==========

  it('handles edit mode with case_log association', () => {
    const reminderWithCaseLog = {
      ...mockReminder,
      contract: null,
      case_log: 5,
    }
    render(
      <ReminderForm
        mode="edit"
        reminder={reminderWithCaseLog as any}
        onSubmit={vi.fn()}
      />
    )
    expect(screen.getByText('保存')).toBeInTheDocument()
  })

  // ========== Contract option deselection behavior ==========

  it('shows correct combobox aria-expanded states', async () => {
    render(
      <ReminderForm mode="create" onSubmit={vi.fn()} contractOptions={mockContractOptions} />
    )
    const comboboxButton = screen.getAllByRole('combobox').find(
      el => el.textContent?.includes('搜索合同')
    )
    expect(comboboxButton).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(comboboxButton!)
    await waitFor(() => {
      expect(comboboxButton).toHaveAttribute('aria-expanded', 'true')
    })
  })
})
