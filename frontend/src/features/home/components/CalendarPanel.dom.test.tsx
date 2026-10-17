// @vitest-environment jsdom
/**
 * CalendarPanel 日历格交互 dom 测试（jsdom）。
 *
 * 用 matchMedia 替身切断点。覆盖手机端（≤760px）「点格子任意位置 = 选中该日开抽屉、
 * 绝不打开新增」与格内标题列表；桌面端「点空白新增 / 点事件行开详情 / 点勾选只切完成态」。
 * 手机端修复背景：以前事件在手机上只是不可交互的圆点，点圆点穿透成新增弹窗，详情永远开不了。
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { CalendarEvent } from '../api'
import { CalendarPanel } from './CalendarPanel'

function installMatchMedia(matches: Record<string, boolean>) {
  window.matchMedia = vi.fn((q: string) => ({
    matches: matches[q] ?? false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  })) as unknown as typeof window.matchMedia
}

function ev(p: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    id: 1,
    kind: 'court',
    kind_label: '庭期',
    title: '张三诉李四合同纠纷开庭',
    content: '开庭',
    day: '2026-10-16',
    time: '09:30',
    time_range: '',
    place: '第三法庭',
    person: '',
    case_no: '',
    hearing_type: '',
    target_type: '案件',
    target_name: '张三诉李四合同纠纷',
    case_id: 7,
    is_today: true,
    is_overdue: false,
    is_completed: false,
    members: 1,
    member_ids: [1],
    can_delete: true,
    ...p,
  }
}

const STATS = { today: 1, today_done: 0, deadline_in_7days: 1, month_court: 3 }

function renderPanel(events: CalendarEvent[]) {
  const handlers = {
    onShiftMonth: vi.fn(),
    onGoToday: vi.fn(),
    onSelectDay: vi.fn(),
    onOpenEvent: vi.fn(),
    onToggleComplete: vi.fn(),
    onOpenAdd: vi.fn(),
  }
  const utils = render(
    <CalendarPanel
      today="2026-10-16"
      view={{ year: 2026, month: 9 }}
      eventsByDay={{ '2026-10-16': events }}
      stats={STATS}
      loading={false}
      {...handlers}
    />,
  )
  return { ...handlers, ...utils }
}

/** 手机端格内标题列表（纯展示块；不能按 aria-hidden 找——lucide 图标 svg 也带 aria-hidden） */
function mobileTitleList(cell: HTMLElement): HTMLElement {
  const list = cell.querySelector<HTMLElement>('[data-calendar-mobile-titles]')
  if (!list) throw new Error('手机端标题列表未渲染')
  return list
}

describe('CalendarPanel 手机断点（≤760px）', () => {
  beforeEach(() => installMatchMedia({ '(max-width: 760px)': true }))

  it('点有安排的格子 = 选中该日（调用方开抽屉），绝不打开新增', () => {
    const { onSelectDay, onOpenAdd, onOpenEvent } = renderPanel([ev()])
    const cell = screen.getByRole('button', { name: '16 日，1 个安排，点按查看该日安排' })

    fireEvent.click(cell)
    expect(onSelectDay).toHaveBeenCalledWith('2026-10-16')
    expect(onOpenAdd).not.toHaveBeenCalled()
    expect(onOpenEvent).not.toHaveBeenCalled()

    // 点在标题行上同样只是选中（标题是纯展示，整格一个点击目标）
    fireEvent.click(within(mobileTitleList(cell)).getByText('张三诉李四合同纠纷开庭'))
    expect(onSelectDay).toHaveBeenCalledTimes(2)
    expect(onOpenAdd).not.toHaveBeenCalled()
  })

  it('点没有安排的格子也只是选中，不新增（新增走抽屉里的「＋新增」）', () => {
    const { onSelectDay, onOpenAdd } = renderPanel([])
    fireEvent.click(screen.getByRole('button', { name: '15 日，点按查看该日安排' }))
    expect(onSelectDay).toHaveBeenCalledWith('2026-10-15')
    expect(onOpenAdd).not.toHaveBeenCalled()
  })

  it('格子里直接显示事项标题，最多 2 条、余下折叠成 +N', () => {
    renderPanel([
      ev({ id: 1, title: '第一件', member_ids: [1] }),
      ev({ id: 2, title: '第二件', member_ids: [2], kind: 'meeting' }),
      ev({ id: 3, title: '第三件', member_ids: [3] }),
    ])
    const cell = screen.getByRole('button', { name: '16 日，3 个安排，点按查看该日安排' })
    const list = within(mobileTitleList(cell))
    expect(list.getByText('第一件')).toBeTruthy()
    expect(list.getByText('第二件')).toBeTruthy()
    expect(list.queryByText('第三件')).toBeNull()
    expect(list.getByText('+1')).toBeTruthy()
  })

  it('键盘 Enter 只选中，不新增', () => {
    const { onSelectDay, onOpenAdd } = renderPanel([ev()])
    fireEvent.keyDown(screen.getByRole('button', { name: '16 日，1 个安排，点按查看该日安排' }), { key: 'Enter' })
    expect(onSelectDay).toHaveBeenCalledWith('2026-10-16')
    expect(onOpenAdd).not.toHaveBeenCalled()
  })
})

describe('CalendarPanel 桌面断点', () => {
  beforeEach(() => installMatchMedia({}))

  it('点格子空白处 → 新增该日安排', () => {
    const { onSelectDay, onOpenAdd } = renderPanel([ev()])
    fireEvent.click(screen.getByRole('button', { name: '16 日，1 个安排，回车新增该日安排' }))
    expect(onOpenAdd).toHaveBeenCalledWith('2026-10-16')
    expect(onSelectDay).not.toHaveBeenCalled()
  })

  it('点事件行 → 打开详情，不新增', () => {
    const { onOpenEvent, onOpenAdd, container } = renderPanel([ev()])
    const row = container.querySelector<HTMLElement>('[data-calendar-event="1"]')
    if (!row) throw new Error('事件行未渲染')
    fireEvent.click(row)
    expect(onOpenEvent).toHaveBeenCalledTimes(1)
    expect(onOpenEvent.mock.calls[0]?.[0]).toMatchObject({ id: 1 })
    expect(onOpenAdd).not.toHaveBeenCalled()
  })

  it('点事件行首的勾选 → 只切换完成态，不开详情也不新增', () => {
    const { onToggleComplete, onOpenEvent, onOpenAdd } = renderPanel([ev()])
    fireEvent.click(screen.getByRole('button', { name: '标记为完成' }))
    expect(onToggleComplete).toHaveBeenCalledTimes(1)
    expect(onOpenEvent).not.toHaveBeenCalled()
    expect(onOpenAdd).not.toHaveBeenCalled()
  })

  it('键盘 Enter = 选中 + 新增', () => {
    const { onSelectDay, onOpenAdd } = renderPanel([])
    fireEvent.keyDown(screen.getByRole('button', { name: '15 日，回车新增该日安排' }), { key: 'Enter' })
    expect(onSelectDay).toHaveBeenCalledWith('2026-10-15')
    expect(onOpenAdd).toHaveBeenCalledWith('2026-10-15')
  })
})
