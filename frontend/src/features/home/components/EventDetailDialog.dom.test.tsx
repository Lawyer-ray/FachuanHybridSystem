// @vitest-environment jsdom
/**
 * EventDetailDialog 删除 / 编辑入口 dom 测试（jsdom）。
 *
 * 覆盖：can_delete=false 不渲染删除按钮（别人建的日程连入口都没有）；
 * can_delete=true 走**弹窗内原地展开**的确认条（不再叠第二层 AlertDialog）——
 * 取消不下发、确认才 onDelete；合并事件的确认文案提示会一起删掉 N 条同步记录；
 * can_edit 显隐编辑入口，编辑表单回填并经 updateReminder 下发。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'

import { updateReminder } from '../api'
import type { CalendarEvent } from '../api'
import { EventDetailDialog } from './EventDetailDialog'

// 编辑表单走 ../api 的 updateReminder / listReminderTypes，测试里全部拦掉
vi.mock('../api', () => ({
  REMINDER_TYPES_KEY: ['reminder-types'],
  listReminderTypes: vi.fn(async () => [{ value: 'other', label: '其他' }]),
  updateReminder: vi.fn(async () => undefined),
}))

function ev(p: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    id: 1,
    kind: 'meeting',
    kind_label: '日程',
    title: '与客户会谈',
    content: '与客户会谈',
    day: '2026-10-20',
    time: '09:00',
    time_range: '',
    place: '',
    person: '',
    case_no: '',
    hearing_type: '',
    target_type: '',
    target_name: '',
    case_id: null,
    is_today: false,
    is_overdue: false,
    is_completed: false,
    reminder_type: 'other',
    members: 1,
    member_ids: [1],
    can_delete: false,
    can_edit: false,
    ...p,
  }
}

function renderDialog(event: CalendarEvent) {
  const onDelete = vi.fn()
  const onSaved = vi.fn()
  const onClose = vi.fn()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <EventDetailDialog
        event={event}
        onClose={onClose}
        onSaved={onSaved}
        onOpenCase={vi.fn()}
        onToggleComplete={vi.fn()}
        onDelete={onDelete}
      />
    </QueryClientProvider>,
  )
  return { onDelete, onSaved, onClose }
}

describe('EventDetailDialog 删除入口', () => {
  it('can_delete=false：不渲染删除按钮', () => {
    renderDialog(ev({ can_delete: false }))
    expect(screen.getByText('与客户会谈')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /删除此安排/ })).toBeNull()
  })

  it('can_delete=true：点删除原地展开确认条，取消不下发，确认才调用 onDelete', async () => {
    const { onDelete } = renderDialog(ev({ can_delete: true }))

    fireEvent.click(screen.getByRole('button', { name: /删除此安排/ }))
    expect(await screen.findByText(/删除后不可恢复/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(onDelete).not.toHaveBeenCalled()
    // 取消后确认条收起，可重新发起
    fireEvent.click(screen.getByRole('button', { name: /删除此安排/ }))
    // 确认条内的「删除」按钮：文案精确为「删除」，与入口的「删除此安排」区分
    fireEvent.click(await screen.findByRole('button', { name: '删除' }))
    expect(onDelete).toHaveBeenCalledTimes(1)
    expect(onDelete.mock.calls[0]?.[0]).toMatchObject({ id: 1, member_ids: [1] })
  })

  it('合并事件：确认文案提示会一起删掉全部同步记录', async () => {
    renderDialog(ev({ can_delete: true, members: 3, member_ids: [1, 2, 3] }))
    fireEvent.click(screen.getByRole('button', { name: /删除此安排/ }))
    expect(await screen.findByText(/同一庭审的 3 条同步记录会一起删除/)).toBeTruthy()
  })
})

describe('EventDetailDialog 编辑入口', () => {
  it('can_edit=false：不渲染编辑按钮', () => {
    renderDialog(ev({ can_edit: false }))
    expect(screen.queryByRole('button', { name: /编辑/ })).toBeNull()
  })

  it('can_edit=true：点编辑原地切表单（回填内容），取消回到详情', () => {
    renderDialog(ev({ can_edit: true }))

    fireEvent.click(screen.getByRole('button', { name: '编辑' }))
    const contentInput = screen.getByPlaceholderText(/提交证据目录/) as HTMLInputElement
    expect(contentInput.value).toBe('与客户会谈')

    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    // 回到详情态：编辑按钮还在，表单输入框没了
    expect(screen.getByRole('button', { name: '编辑' })).toBeTruthy()
    expect(screen.queryByPlaceholderText(/提交证据目录/)).toBeNull()
  })

  it('保存：经 updateReminder 下发四项字段，成功后回调 onSaved', async () => {
    const { onSaved } = renderDialog(ev({ can_edit: true, content: '旧内容', day: '2026-10-21', time: '09:00' }))

    fireEvent.click(screen.getByRole('button', { name: '编辑' }))
    const contentInput = screen.getByPlaceholderText(/提交证据目录/) as HTMLInputElement
    fireEvent.change(contentInput, { target: { value: '新内容' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() => {
      expect(updateReminder).toHaveBeenCalledTimes(1)
    })
    expect(vi.mocked(updateReminder)).toHaveBeenCalledWith(1, {
      reminder_type: 'other',
      content: '新内容',
      due_at: '2026-10-21T09:00:00',
    })
    await waitFor(() => {
      expect(onSaved).toHaveBeenCalledTimes(1)
    })
  })
})
