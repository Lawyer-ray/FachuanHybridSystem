// @vitest-environment jsdom
/**
 * EventEditForm 测试（jsdom）。
 *
 * 日历事件的编辑表单：改类型/内容/日期/时刻/关联对象，提交走 PUT /reminders/{id}。
 * 核心不变量：
 * - canSave：内容非空 + 日期 YYYY-MM-DD + 时刻 HH:mm + 非 busy
 * - 存量类型不在枚举里时补一个原值 option（防止 select 静默归零）
 * - 提交成功提示并回调 onSaved；失败提示且复位 busy、不回调
 * - 回车在可保存时提交
 * - 关联对象：已绑定回显、未绑定显示「未关联」、选中后 payload 带 target_type/target_id、
 *   没动过则 payload 不带任何关联字段（后端 exclude_unset 保持原绑定）
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  updateReminder: vi.fn(),
  listReminderTypes: vi.fn(async () => [
    { value: 'other', label: '其他' },
    { value: 'hearing', label: '开庭' },
  ]),
  searchTargetOptions: vi.fn(async (): Promise<TargetOption[]> => []),
  REMINDER_TYPES_KEY: ['reminder-types'],
}))

vi.mock('../api', () => ({ ...apiMock }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))

import { toast } from 'sonner'

import { EventEditForm } from './EventEditForm'
import type { CalendarEvent, TargetOption } from '../api'

function ev(over: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    id: 9,
    kind: 'meeting',
    title: '与客户会谈',
    content: '与客户会谈',
    day: '2026-10-20',
    time: '09:00',
    reminder_type: 'other',
    ...over,
  } as CalendarEvent
}

function wrap(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

function renderForm(props: Partial<Parameters<typeof EventEditForm>[0]> = {}) {
  const onSaved = vi.fn()
  const onCancel = vi.fn()
  const utils = render(wrap(<EventEditForm event={ev()} onSaved={onSaved} onCancel={onCancel} {...props} />))
  return { ...utils, onSaved, onCancel }
}

function contentInput(): HTMLInputElement {
  return screen.getByPlaceholderText(/提交证据目录/) as HTMLInputElement
}

function saveButton(): HTMLButtonElement {
  return screen.getByRole('button', { name: /保存/ }) as HTMLButtonElement
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.updateReminder.mockResolvedValue(undefined)
  apiMock.searchTargetOptions.mockResolvedValue([])
})

describe('EventEditForm：回填与 canSave', () => {
  it('打开时回填内容/日期/时刻/类型', () => {
    const { container } = renderForm()
    expect(contentInput().value).toBe('与客户会谈')
    // date/time 输入按值回填（用 type 精确选取，避免与内容框顺序耦合）
    const dateInput = container.querySelector('input[type="date"]') as HTMLInputElement
    const timeInput = container.querySelector('input[type="time"]') as HTMLInputElement
    expect(dateInput.value).toBe('2026-10-20')
    expect(timeInput.value).toBe('09:00')
    container.remove()
  })

  it('内容清空后保存禁用', () => {
    const { container } = renderForm()
    fireEvent.change(contentInput(), { target: { value: '   ' } })
    expect(saveButton().disabled).toBe(true)
    container.remove()
  })

  it('日期被清空后保存禁用', () => {
    const { container } = renderForm()
    const dateInput = Array.from(container.querySelectorAll('input[type="date"]'))[0] as HTMLInputElement
    fireEvent.change(dateInput, { target: { value: '' } })
    expect(saveButton().disabled).toBe(true)
    container.remove()
  })

  it('时刻被清空后保存禁用', () => {
    const { container } = renderForm()
    const timeInput = Array.from(container.querySelectorAll('input[type="time"]'))[0] as HTMLInputElement
    fireEvent.change(timeInput, { target: { value: '' } })
    expect(saveButton().disabled).toBe(true)
    container.remove()
  })

  it('内容/日期/时刻齐备时保存可用', () => {
    const { container } = renderForm()
    expect(saveButton().disabled).toBe(false)
    container.remove()
  })
})

describe('EventEditForm：类型选项', () => {
  it('存量类型不在枚举里时补原值 option', async () => {
    const { container } = renderForm({ event: ev({ reminder_type: 'legacy_type' }) })
    await waitFor(() => expect(apiMock.listReminderTypes).toHaveBeenCalled())

    const select = container.querySelector('select') as HTMLSelectElement
    const values = Array.from(select.options).map((o) => o.value)
    expect(values).toContain('legacy_type')
    expect(select.value).toBe('legacy_type')
    container.remove()
  })

  it('类型在枚举里时不补重复 option', async () => {
    const { container } = renderForm({ event: ev({ reminder_type: 'hearing' }) })
    await waitFor(() => expect(apiMock.listReminderTypes).toHaveBeenCalled())

    const select = container.querySelector('select') as HTMLSelectElement
    const values = Array.from(select.options).map((o) => o.value)
    expect(values.filter((v) => v === 'hearing')).toHaveLength(1)
    container.remove()
  })
})

describe('EventEditForm：关联对象回显', () => {
  it('已绑定时回显类型标签与对象名', () => {
    const { container } = renderForm({
      event: ev({ target_type: '案件', target_name: '张三诉李四案' }),
    })
    expect(container.textContent).toContain('关联对象')
    expect(container.textContent).toContain('张三诉李四案')
    // 未点「修改」时就是展示行，不出检索框
    expect(container.querySelector('[role="combobox"]')).toBeNull()
    container.remove()
  })

  it('未绑定时显示「未关联」而不是空白', () => {
    const { container } = renderForm({ event: ev({ target_type: '', target_name: '' }) })
    expect(container.textContent).toContain('关联对象')
    // 类型徽标与名称都退回「未关联」，不留空白；两个 span 各一处
    expect(screen.getAllByText('未关联')).toHaveLength(2)
    container.remove()
  })

  it('未绑定点「选择」展开检索框，输入关键字后展示候选', async () => {
    apiMock.searchTargetOptions.mockResolvedValue([
      { id: 1, target_type: 'case', target_type_label: '案件', title: '张三诉李四', hint: '' },
    ])
    const { container } = renderForm({ event: ev({ target_type: '', target_name: '' }) })

    fireEvent.click(screen.getByRole('button', { name: '选择' }))
    const input = container.querySelector('[role="combobox"]') as HTMLInputElement
    fireEvent.change(input, { target: { value: '张三' } })

    await waitFor(() => expect(container.textContent).toContain('张三诉李四'), { timeout: 3000 })
    container.remove()
  })
})

describe('EventEditForm：关联对象提交', () => {
  it('未绑定→选中新关联对象：payload 带 target_type/target_id（拆解交给 api 层）', async () => {
    apiMock.searchTargetOptions.mockResolvedValue([
      { id: 7, target_type: 'case', target_type_label: '案件', title: '王五案', hint: '' },
    ])
    const { container } = renderForm({ event: ev({ target_type: '', target_name: '' }) })

    fireEvent.click(screen.getByRole('button', { name: '选择' }))
    const input = container.querySelector('[role="combobox"]') as HTMLInputElement
    fireEvent.change(input, { target: { value: '王五' } })
    await waitFor(() => expect(container.textContent).toContain('王五案'), { timeout: 3000 })

    const option = Array.from(container.querySelectorAll('[role="option"]')).find((o) =>
      o.textContent?.includes('王五案'),
    ) as HTMLElement
    fireEvent.click(option)

    fireEvent.click(saveButton())
    await waitFor(() =>
      expect(apiMock.updateReminder).toHaveBeenCalledWith(
        9,
        expect.objectContaining({ target_type: 'case', target_id: 7 }),
      ),
    )
    // toast 把换绑结果写清楚，避免「保存了但不知道绑没绑上」
    expect(toast.success).toHaveBeenCalledWith('已保存 · 案件：王五案')
    container.remove()
  })

  it('没动关联对象：payload 不带任何关联字段（保持原绑定）', async () => {
    const { container } = renderForm({ event: ev({ target_type: '案件', target_name: '张三诉李四案' }) })
    fireEvent.click(saveButton())

    await waitFor(() => expect(apiMock.updateReminder).toHaveBeenCalled())
    const payload = apiMock.updateReminder.mock.calls[0]![1]
    expect(payload).not.toHaveProperty('target_type')
    expect(payload).not.toHaveProperty('target_id')
    expect(payload).not.toHaveProperty('clear_target')
    expect(apiMock.searchTargetOptions).not.toHaveBeenCalled()
    container.remove()
  })

  it('点「解除关联」后保存：payload 带 clear_target，toast 说明已解除', async () => {
    const { container } = renderForm({ event: ev({ target_type: '案件', target_name: '张三诉李四案' }) })
    fireEvent.click(screen.getByRole('button', { name: '解除关联' }))
    fireEvent.click(saveButton())

    await waitFor(() =>
      expect(apiMock.updateReminder).toHaveBeenCalledWith(9, expect.objectContaining({ clear_target: true })),
    )
    expect(toast.success).toHaveBeenCalledWith('已保存 · 已解除关联')
    container.remove()
  })
})

describe('EventEditForm：提交', () => {
  it('点保存：提交 trim 后的内容与拼好的 due_at', async () => {
    const { container, onSaved } = renderForm()
    fireEvent.change(contentInput(), { target: { value: '  新内容  ' } })
    fireEvent.click(saveButton())

    await waitFor(() =>
      expect(apiMock.updateReminder).toHaveBeenCalledWith(9, {
        reminder_type: 'other',
        content: '新内容',
        due_at: '2026-10-20T09:00:00',
      }),
    )
    expect(toast.success).toHaveBeenCalledWith('已保存')
    expect(onSaved).toHaveBeenCalled()
    container.remove()
  })

  it('改日期与时刻后 due_at 随之更新', async () => {
    const { container } = renderForm()
    const dateInput = Array.from(container.querySelectorAll('input[type="date"]'))[0] as HTMLInputElement
    const timeInput = Array.from(container.querySelectorAll('input[type="time"]'))[0] as HTMLInputElement
    fireEvent.change(dateInput, { target: { value: '2026-11-01' } })
    fireEvent.change(timeInput, { target: { value: '14:30' } })
    fireEvent.click(saveButton())

    await waitFor(() =>
      expect(apiMock.updateReminder).toHaveBeenCalledWith(
        9,
        expect.objectContaining({ due_at: '2026-11-01T14:30:00' }),
      ),
    )
    container.remove()
  })

  it('回车提交（可保存时）', async () => {
    const { container } = renderForm()
    fireEvent.keyDown(contentInput(), { key: 'Enter' })
    await waitFor(() => expect(apiMock.updateReminder).toHaveBeenCalled())
    container.remove()
  })

  it('空内容回车不提交', async () => {
    const { container } = renderForm()
    fireEvent.change(contentInput(), { target: { value: '  ' } })
    fireEvent.keyDown(contentInput(), { key: 'Enter' })
    await new Promise((r) => setTimeout(r, 30))
    expect(apiMock.updateReminder).not.toHaveBeenCalled()
    container.remove()
  })

  it('提交失败：提示且不回调、busy 复位', async () => {
    apiMock.updateReminder.mockRejectedValue(new Error('后端拒绝'))
    const { container, onSaved } = renderForm()
    fireEvent.click(saveButton())

    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    expect(onSaved).not.toHaveBeenCalled()
    // busy 复位后按钮重新可用
    await waitFor(() => expect(saveButton().disabled).toBe(false))
    container.remove()
  })

  it('点取消回调 onCancel', () => {
    const { container, onCancel } = renderForm()
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(onCancel).toHaveBeenCalled()
    container.remove()
  })
})
