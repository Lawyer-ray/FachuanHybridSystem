// @vitest-environment jsdom
/**
 * AddReminderDialog 测试（jsdom）。
 *
 * 核心不变量：
 * - canSave：内容非空 + 时刻形如 HH:mm + 非 busy，三者同时满足
 * - 打开时重置表单（不残留上次输入）
 * - tab 过滤候选（all / contract / case / case_log）
 * - 选中关联对象后候选收起、保存时带上 target_type/target_id
 * - 提交成功后回调 onSaved + onClose
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  createReminder: vi.fn(),
  listReminderTypes: vi.fn(async (): Promise<Array<{ value: string; label: string }>> => [
    { value: 'other', label: '其他' },
    { value: 'hearing', label: '开庭' },
  ]),
  searchTargetOptions: vi.fn(async (): Promise<TargetOption[]> => []),
  REMINDER_TYPES_KEY: ['reminder-types'],
}))

vi.mock('../api', () => ({ ...apiMock }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }))

import { toast } from 'sonner'

import { AddReminderDialog } from './AddReminderDialog'
import type { TargetOption } from '../api'

function renderDialog(props: Partial<Parameters<typeof AddReminderDialog>[0]> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrap = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )
  const onClose = vi.fn()
  const onSaved = vi.fn()
  const utils = render(
    <AddReminderDialog day="2026-10-20" defaultTime="09:30" onClose={onClose} onSaved={onSaved} {...props} />,
    { wrapper: wrap },
  )
  return { ...utils, onClose, onSaved }
}

function saveButton(): HTMLButtonElement {
  return Array.from(document.querySelectorAll('button')).find((b) =>
    /保存|添加/.test(b.textContent ?? ''),
  ) as HTMLButtonElement
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.listReminderTypes.mockResolvedValue([
    { value: 'other', label: '其他' },
    { value: 'hearing', label: '开庭' },
  ])
  apiMock.searchTargetOptions.mockResolvedValue([])
})

describe('AddReminderDialog：关闭态', () => {
  it('day=null 时不渲染内容', () => {
    const { container } = renderDialog({ day: null })
    expect(container.textContent).toBe('')
    container.remove()
  })
})

describe('AddReminderDialog：canSave 判定', () => {
  it('内容为空时保存按钮禁用', async () => {
    const { container } = renderDialog()
    await waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeTruthy())
    expect(saveButton().disabled).toBe(true)
    container.remove()
  })

  it('只有空白内容也禁用', async () => {
    const { container } = renderDialog()
    await waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeTruthy())

    const contentInput = screen.getByPlaceholderText(/提交证据目录/)
    fireEvent.change(contentInput, { target: { value: '   ' } })
    expect(saveButton().disabled).toBe(true)
    container.remove()
  })

  it('内容非空且时刻合法时启用', async () => {
    const { container } = renderDialog()
    await waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeTruthy())

    const contentInput = screen.getByPlaceholderText(/提交证据目录/)
    fireEvent.change(contentInput, { target: { value: '开庭提醒' } })
    await waitFor(() => expect(saveButton().disabled).toBe(false))
    container.remove()
  })
})

describe('AddReminderDialog：提交', () => {
  it('提交成功调用 createReminder 并带日期时间与空关联', async () => {
    apiMock.createReminder.mockResolvedValue({})
    const { container, onSaved, onClose } = renderDialog()
    await waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeTruthy())

    const contentInput = screen.getByPlaceholderText(/提交证据目录/)
    fireEvent.change(contentInput, { target: { value: '开庭提醒' } })
    fireEvent.click(saveButton())

    await waitFor(() =>
      expect(apiMock.createReminder).toHaveBeenCalledWith(
        expect.objectContaining({
          content: '开庭提醒',
          due_at: '2026-10-20T09:30:00',
          target_type: null,
          target_id: null,
        }),
      ),
    )
    expect(onSaved).toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
    expect(toast.success).toHaveBeenCalled()
    container.remove()
  })

  it('提交失败弹错误 toast 且不关闭弹窗', async () => {
    apiMock.createReminder.mockRejectedValue(new Error('后端拒绝'))
    const { container, onClose } = renderDialog()
    await waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeTruthy())

    const contentInput = screen.getByPlaceholderText(/提交证据目录/)
    fireEvent.change(contentInput, { target: { value: '开庭提醒' } })
    fireEvent.click(saveButton())

    await waitFor(() => expect(toast.error).toHaveBeenCalled())
    expect(onClose).not.toHaveBeenCalled()
    container.remove()
  })
})

describe('AddReminderDialog：关联对象', () => {
  it('输入关键字后展示候选', async () => {
    apiMock.searchTargetOptions.mockResolvedValue([
      { id: 1, target_type: 'case', target_type_label: '案件', title: '张三诉李四', hint: '' },
    ])
    const { container } = renderDialog()
    await waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeTruthy())

    const input = document.querySelector('[role="combobox"]') as HTMLInputElement
    fireEvent.change(input, { target: { value: '张三' } })

    await waitFor(() => expect(document.body.textContent).toContain('张三诉李四'), { timeout: 3000 })
    container.remove()
  })

  it('选中候选后保存带上 target_type/target_id', async () => {
    apiMock.searchTargetOptions.mockResolvedValue([
      { id: 7, target_type: 'case', target_type_label: '案件', title: '王五案', hint: '' },
    ])
    apiMock.createReminder.mockResolvedValue({})
    const { container } = renderDialog()
    await waitFor(() => expect(document.querySelector('[role="dialog"]')).toBeTruthy())

    const input = document.querySelector('[role="combobox"]') as HTMLInputElement
    fireEvent.change(input, { target: { value: '王五' } })
    await waitFor(() => expect(document.body.textContent).toContain('王五案'), { timeout: 3000 })

    const option = Array.from(document.querySelectorAll('[role="option"]')).find((o) =>
      o.textContent?.includes('王五案'),
    ) as HTMLElement
    fireEvent.click(option)

    const contentInput = screen.getByPlaceholderText(/提交证据目录/)
    fireEvent.change(contentInput, { target: { value: '开庭提醒' } })
    fireEvent.click(saveButton())

    await waitFor(() =>
      expect(apiMock.createReminder).toHaveBeenCalledWith(
        expect.objectContaining({ target_type: 'case', target_id: 7 }),
      ),
    )
    container.remove()
  })
})
