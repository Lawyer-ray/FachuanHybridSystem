// @vitest-environment jsdom
/**
 * EventDetailDialog 删除入口 dom 测试（jsdom）。
 *
 * 覆盖：can_delete=false 不渲染删除按钮（别人建的日程连入口都没有）；
 * can_delete=true 走 AlertDialog 二次确认——取消不下发、确认才 onDelete；
 * 合并事件的确认文案提示会一起删掉 N 条同步记录。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { CalendarEvent } from '../api'
import { EventDetailDialog } from './EventDetailDialog'

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
    members: 1,
    member_ids: [1],
    can_delete: false,
    ...p,
  }
}

function renderDialog(event: CalendarEvent) {
  const onDelete = vi.fn()
  render(
    <EventDetailDialog event={event} onClose={vi.fn()} onOpenCase={vi.fn()} onToggleComplete={vi.fn()} onDelete={onDelete} />,
  )
  return { onDelete }
}

describe('EventDetailDialog 删除入口', () => {
  it('can_delete=false：不渲染删除按钮', () => {
    renderDialog(ev({ can_delete: false }))
    expect(screen.getByText('与客户会谈')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /删除此安排/ })).toBeNull()
  })

  it('can_delete=true：点删除先弹确认，取消不下发，确认才调用 onDelete', async () => {
    const { onDelete } = renderDialog(ev({ can_delete: true }))

    fireEvent.click(screen.getByRole('button', { name: /删除此安排/ }))
    expect(await screen.findByText(/删除后不可恢复/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(onDelete).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: /删除此安排/ }))
    // 确认弹窗内的「删除」按钮：文案精确为「删除」，与入口的「删除此安排」区分
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
