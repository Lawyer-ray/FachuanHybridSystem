// @vitest-environment jsdom
/**
 * EventContextMenu 右键快捷菜单 dom 测试（jsdom）。
 *
 * 覆盖：菜单项按权限显隐（can_delete=false 无删除项）、标记完成 / 删除各自
 * 回调并收起菜单、合并事件删除项带条数提示、点遮罩 / ESC 收起。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { CalendarEvent } from '../api'
import { EventContextMenu } from './EventContextMenu'

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
    can_delete: true,
    can_edit: true,
    ...p,
  }
}

const TARGET = { x: 200, y: 180 }

function renderMenu(event: CalendarEvent | null) {
  const handlers = { onClose: vi.fn(), onToggleComplete: vi.fn(), onDelete: vi.fn() }
  const { container } = render(
    <EventContextMenu target={event ? { event, ...TARGET } : null} {...handlers} />,
  )
  return { ...handlers, container }
}

describe('EventContextMenu', () => {
  it('can_delete=true：两项都在，删除项带合并条数提示', () => {
    renderMenu(ev({ members: 3, member_ids: [1, 2, 3] }))
    expect(screen.getByRole('menuitem', { name: /标记完成/ })).toBeTruthy()
    const deleteItem = screen.getByRole('menuitem', { name: /删除/ })
    expect(deleteItem.textContent).toContain('共 3 条')
  })

  it('can_delete=false：只有标记完成，没有删除项', () => {
    renderMenu(ev({ can_delete: false }))
    expect(screen.getByRole('menuitem', { name: /标记完成/ })).toBeTruthy()
    expect(screen.queryByRole('menuitem', { name: /删除/ })).toBeNull()
  })

  it('已完成事件：菜单项变为「恢复为未完成」', () => {
    renderMenu(ev({ is_completed: true }))
    expect(screen.getByRole('menuitem', { name: /恢复为未完成/ })).toBeTruthy()
  })

  it('点标记完成：回调后收起菜单', () => {
    const event = ev()
    const { onToggleComplete, onClose } = renderMenu(event)
    fireEvent.click(screen.getByRole('menuitem', { name: /标记完成/ }))
    expect(onToggleComplete).toHaveBeenCalledWith(event)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('点删除：回调原事件（含全部 member_ids）后收起', () => {
    const event = ev({ members: 2, member_ids: [1, 2] })
    const { onDelete, onClose } = renderMenu(event)
    fireEvent.click(screen.getByRole('menuitem', { name: /删除/ }))
    expect(onDelete).toHaveBeenCalledWith(event)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('点透明遮罩：只收起菜单，不触发任何操作', () => {
    const { container, onClose, onDelete, onToggleComplete } = renderMenu(ev())
    fireEvent.click(container.firstChild as HTMLElement)
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onDelete).not.toHaveBeenCalled()
    expect(onToggleComplete).not.toHaveBeenCalled()
  })

  it('ESC：收起菜单', () => {
    const { onClose } = renderMenu(ev())
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('target=null：不渲染任何内容', () => {
    const { container } = renderMenu(null)
    expect(container.firstChild).toBeNull()
  })
})
