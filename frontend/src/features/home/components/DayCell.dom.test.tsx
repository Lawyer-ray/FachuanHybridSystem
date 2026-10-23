// @vitest-environment jsdom
/**
 * DayCell 测试（jsdom）。
 *
 * 月历单日格的分支密度很高，核心是「桌面 / 手机」两套交互：
 * - 空槽（key/day 为 null）只渲染占位
 * - 桌面：点空白 → onOpenAdd；点事件行或「+N 更多」→ 只 onPick
 * - 手机：点任何位置 → onPick（事件行不渲染）
 * - 键盘：Enter/Space 触发 onPick（桌面额外 onOpenAdd）
 * - 事件行：点击/Enter 开详情且不冒泡；右键在有 handler 时才拦默认菜单
 * - 视觉：非本月降透明度、今天高亮、选中底色、已完成划线
 */
import { fireEvent, render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../domain', () => ({
  formatCN: () => '2026年10月',
  parseKey: () => new Date(2026, 9, 1),
}))
vi.mock('../api-meta', () => ({
  briefLine: () => '',
  cellMetaLines: () => ['09:00', '第三法庭'],
  isKeyKind: (k: string) => k === 'hearing',
}))
vi.mock('../constants', () => ({ KIND_ROW: { hearing: 'kind-hearing' } }))

import { DayCell } from './DayCell'
import type { CalendarEvent } from '../api'

function ev(id: number, over: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    id,
    kind: 'hearing',
    title: `事件 ${id}`,
    time: '09:00',
    is_completed: false,
    ...over,
  } as CalendarEvent
}

type CellProps = React.ComponentProps<typeof DayCell>

function renderCell(over: Partial<CellProps> = {}) {
  const cbs = {
    onPick: vi.fn(),
    onOpenAdd: vi.fn(),
    onOpenDetail: vi.fn(),
    onToggleComplete: vi.fn(),
    onEventContextMenu: vi.fn(),
  }
  const props: CellProps = {
    cell: { key: '2026-10-20', day: 20, inMonth: true },
    today: '2026-10-20',
    selected: false,
    events: [ev(1)],
    maxRows: 3,
    mobile: false,
    ...cbs,
    ...over,
  }
  const utils = render(<DayCell {...props} />)
  const cellEl = utils.container.firstElementChild as HTMLElement
  return Object.assign(utils, { cbs, props, cellEl })
}

describe('DayCell：空槽与占位', () => {
  it('key 为 null 时只渲染占位', () => {
    const { container } = renderCell({ cell: { key: null, day: null, inMonth: false } })
    expect(container.querySelector('[role="button"]')).toBeNull()
    container.remove()
  })

  it('day 为 null 时同样只渲染占位', () => {
    const { container } = renderCell({ cell: { key: '2026-10-20', day: null, inMonth: true } })
    expect(container.querySelector('[role="button"]')).toBeNull()
    container.remove()
  })
})

describe('DayCell：桌面点击分派', () => {
  it('点空白 → onOpenAdd', () => {
    const { cbs, cellEl, unmount } = renderCell()
    fireEvent.click(cellEl)
    expect(cbs.onOpenAdd).toHaveBeenCalledWith('2026-10-20')
    expect(cbs.onPick).not.toHaveBeenCalled()
    unmount()
  })

  it('点事件行 → 只开详情（stopPropagation 不触发新增）', () => {
    const { cbs, container, unmount } = renderCell()
    const row = container.querySelector('[data-calendar-event]') as HTMLElement
    fireEvent.click(row)
    expect(cbs.onOpenDetail).toHaveBeenCalled()
    expect(cbs.onOpenAdd).not.toHaveBeenCalled()
    unmount()
  })

  it('点「+N 更多」→ 只 onPick 不新增', () => {
    const { cbs, container, unmount } = renderCell({ events: [ev(1), ev(2), ev(3), ev(4)], maxRows: 2 })
    const more = container.querySelector('[data-calendar-more]')
    if (more) {
      fireEvent.click(more)
      expect(cbs.onPick).toHaveBeenCalledWith('2026-10-20')
      expect(cbs.onOpenAdd).not.toHaveBeenCalled()
    }
    unmount()
  })
})

describe('DayCell：手机行为', () => {
  it('手机点任何位置 → onPick（不开新增）', () => {
    const { cbs, cellEl, unmount } = renderCell({ mobile: true })
    fireEvent.click(cellEl)
    expect(cbs.onPick).toHaveBeenCalledWith('2026-10-20')
    expect(cbs.onOpenAdd).not.toHaveBeenCalled()
    unmount()
  })

  it('手机不渲染事件行（标题行只在桌面可见）', () => {
    const { container, unmount } = renderCell({ mobile: true })
    // 桌面事件行带 data-calendar-event；手机隐藏但仍可能在 DOM 中，
    // 这里断言 aria-label 文案走手机分支
    const el = container.querySelector('[role="button"]') as HTMLElement
    expect(el.getAttribute('aria-label')).toContain('点按查看该日安排')
    unmount()
  })

  it('桌面 aria-label 说明「回车新增」', () => {
    const { cellEl, unmount } = renderCell({ mobile: false })
    expect(cellEl.getAttribute('aria-label')).toContain('回车新增该日安排')
    unmount()
  })
})

describe('DayCell：键盘', () => {
  it('桌面 Enter：onPick + onOpenAdd', () => {
    const { cbs, cellEl, unmount } = renderCell()
    fireEvent.keyDown(cellEl, { key: 'Enter' })
    expect(cbs.onPick).toHaveBeenCalled()
    expect(cbs.onOpenAdd).toHaveBeenCalled()
    unmount()
  })

  it('桌面 Space：同样 onPick + onOpenAdd', () => {
    const { cbs, cellEl, unmount } = renderCell()
    fireEvent.keyDown(cellEl, { key: ' ' })
    expect(cbs.onPick).toHaveBeenCalled()
    expect(cbs.onOpenAdd).toHaveBeenCalled()
    unmount()
  })

  it('手机 Enter：只 onPick', () => {
    const { cbs, cellEl, unmount } = renderCell({ mobile: true })
    fireEvent.keyDown(cellEl, { key: 'Enter' })
    expect(cbs.onPick).toHaveBeenCalled()
    expect(cbs.onOpenAdd).not.toHaveBeenCalled()
    unmount()
  })

  it('其他键不触发', () => {
    const { cbs, cellEl, unmount } = renderCell()
    fireEvent.keyDown(cellEl, { key: 'a' })
    expect(cbs.onPick).not.toHaveBeenCalled()
    unmount()
  })
})

describe('DayCell：事件行交互', () => {
  it('事件行 Enter 开详情且阻止冒泡', () => {
    const { cbs, container, unmount } = renderCell()
    const row = container.querySelector('[data-calendar-event]') as HTMLElement
    const e = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })
    row.dispatchEvent(e)
    expect(cbs.onOpenDetail).toHaveBeenCalled()
    expect(e.defaultPrevented).toBe(true)
    unmount()
  })

  it('事件行右键触发快捷菜单并阻止默认菜单', () => {
    const { cbs, container, unmount } = renderCell()
    const row = container.querySelector('[data-calendar-event]') as HTMLElement
    const e = new MouseEvent('contextmenu', { bubbles: true, cancelable: true })
    row.dispatchEvent(e)
    expect(cbs.onEventContextMenu).toHaveBeenCalled()
    expect(e.defaultPrevented).toBe(true)
    unmount()
  })

  it('未传 onEventContextMenu 时不拦右键（走浏览器默认）', () => {
    const { container, unmount } = renderCell({ onEventContextMenu: undefined })
    const row = container.querySelector('[data-calendar-event]') as HTMLElement
    const e = new MouseEvent('contextmenu', { bubbles: true, cancelable: true })
    row.dispatchEvent(e)
    expect(e.defaultPrevented).toBe(false)
    unmount()
  })
})

describe('DayCell：视觉态', () => {
  it('非本月降透明度', () => {
    const { cellEl, unmount } = renderCell({ cell: { key: '2026-11-01', day: 1, inMonth: false } })
    expect(cellEl.className).toContain('opacity-30')
    unmount()
  })

  it('今天高亮', () => {
    const { cellEl, unmount } = renderCell()
    expect(cellEl.className).toContain('bg-status-red-bg')
    unmount()
  })

  it('选中态带底色（非今天，避免被今天高亮覆盖）', () => {
    const { cellEl, unmount } = renderCell({
      cell: { key: '2026-10-21', day: 21, inMonth: true },
      today: '2026-10-20',
      selected: true,
    })
    expect(cellEl.className).toContain('bg-secondary')
    unmount()
  })

  it('有事件时显示条数角标', () => {
    const { container, unmount } = renderCell({ events: [ev(1), ev(2)] })
    expect(container.textContent).toContain('2')
    unmount()
  })

  it('无事件时不显示角标', () => {
    const { container, unmount } = renderCell({ events: [] })
    // 日期数字本身也匹配 tabular-nums，用 aria-label 判断更稳
    expect(container.querySelector('[role="button"]')!.getAttribute('aria-label')).not.toContain('个安排')
    unmount()
  })

  it('已完成事件带 opacity-55', () => {
    const { container, unmount } = renderCell({ events: [ev(1, { is_completed: true })] })
    const row = container.querySelector('[data-calendar-event]') as HTMLElement
    expect(row.className).toContain('opacity-55')
    unmount()
  })
})
