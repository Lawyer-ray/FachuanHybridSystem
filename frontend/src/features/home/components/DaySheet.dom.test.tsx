// @vitest-environment jsdom
/**
 * DaySheet 底部抽屉测试（jsdom）。
 *
 * 覆盖：关闭态不显示日期、今日标记、条数文案、空态、勾选不冒泡触发打开、
 * 键盘 Enter/Space 打开详情、新增与关闭按钮。
 */
import { fireEvent, render, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { CalendarEvent } from '../api'
import { DaySheet } from './DaySheet'

function ev(over: Partial<CalendarEvent> = {}): CalendarEvent {
  return {
    id: 1,
    kind: 'hearing',
    title: '开庭',
    date: '2026-10-20',
    time: '09:30',
    is_completed: false,
    ...over,
  } as CalendarEvent
}

function renderSheet(props: Partial<Parameters<typeof DaySheet>[0]> = {}) {
  return render(
    <DaySheet
      day="2026-10-20"
      today="2026-10-20"
      events={[]}
      onClose={vi.fn()}
      onOpenEvent={vi.fn()}
      onToggleComplete={vi.fn()}
      onAdd={vi.fn()}
      {...props}
    />,
  )
}

describe('DaySheet', () => {
  it('关闭态（day=null）：不渲染日期文案', () => {
    const { container } = renderSheet({ day: null })
    expect(container.textContent).not.toContain('今天')
    container.remove()
  })

  it('当天为 today 时显示「· 今天」', () => {
    const { container } = renderSheet({ today: '2026-10-20' })
    expect(within(container).getByText('· 今天')).toBeTruthy()
    container.remove()
  })

  it('非今天不显示今日标记', () => {
    const { container } = renderSheet({ day: '2026-10-21', today: '2026-10-20' })
    expect(container.textContent).not.toContain('· 今天')
    container.remove()
  })

  it('空态：提示新增', () => {
    const { container } = renderSheet({ events: [] })
    expect(within(container).getByText('暂无安排')).toBeTruthy()
    expect(within(container).getByText(/这一天没有安排/)).toBeTruthy()
    container.remove()
  })

  it('有安排时显示条数与标题', () => {
    const { container } = renderSheet({ events: [ev({ id: 1 }), ev({ id: 2, title: '会见' })] })
    expect(within(container).getByText('2 条安排')).toBeTruthy()
    expect(within(container).getByText('开庭')).toBeTruthy()
    expect(within(container).getByText('会见')).toBeTruthy()
    container.remove()
  })

  it('点勾选只触发 onToggleComplete，不冒泡去打开详情', () => {
    const onToggleComplete = vi.fn()
    const onOpenEvent = vi.fn()
    const e = ev()
    const { container } = renderSheet({ events: [e], onToggleComplete, onOpenEvent })

    fireEvent.click(within(container).getByRole('button', { name: '标记为完成' }))
    expect(onToggleComplete).toHaveBeenCalledWith(e)
    expect(onOpenEvent).not.toHaveBeenCalled()
    container.remove()
  })

  it('回车与空格打开详情（role=button 的键盘语义）', () => {
    const onOpenEvent = vi.fn()
    const e = ev()
    const { container } = renderSheet({ events: [e], onOpenEvent })

    const row = within(container).getByText('开庭').closest('[role="button"]') as HTMLElement
    fireEvent.keyDown(row, { key: 'Enter' })
    expect(onOpenEvent).toHaveBeenCalledWith(e)

    fireEvent.keyDown(row, { key: ' ' })
    expect(onOpenEvent).toHaveBeenCalledTimes(2)
    container.remove()
  })

  it('新增与关闭按钮各自回调', () => {
    const onAdd = vi.fn()
    const onClose = vi.fn()
    const { container } = renderSheet({ onAdd, onClose })

    fireEvent.click(within(container).getByRole('button', { name: '＋ 新增' }))
    expect(onAdd).toHaveBeenCalledTimes(1)

    fireEvent.click(within(container).getByRole('button', { name: '关闭' }))
    expect(onClose).toHaveBeenCalledTimes(1)
    container.remove()
  })

  it('已完成事件：勾选按钮语义为「标记为未完成」', () => {
    const { container } = renderSheet({ events: [ev({ is_completed: true })] })
    expect(within(container).getByRole('button', { name: '标记为未完成' })).toBeTruthy()
    container.remove()
  })
})
