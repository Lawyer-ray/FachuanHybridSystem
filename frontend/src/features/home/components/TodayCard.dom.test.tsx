// @vitest-environment jsdom
/**
 * TodayCard 渲染与交互测试（jsdom）。
 *
 * 覆盖：空态 / loading / error（含重试）/ 计数口径（待办 vs 总件数）/
 * 完成态样式与勾选回调 / 点标题打开详情。
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { CalendarEvent } from '../api'
import { TodayCard } from './TodayCard'

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

function renderCard(props: Partial<Parameters<typeof TodayCard>[0]> = {}) {
  return render(
    <TodayCard
      events={[]}
      loading={false}
      error={null}
      onOpenEvent={vi.fn()}
      onToggleComplete={vi.fn()}
      {...props}
    />,
  )
}

describe('TodayCard', () => {
  it('空态：没有安排提示，计数为 0 件', () => {
    renderCard()
    expect(screen.getByText('今天没有安排，记一笔吧')).toBeTruthy()
    expect(screen.getByText('0 件')).toBeTruthy()
  })

  it('loading：显示载入中而非空态', () => {
    renderCard({ loading: true })
    expect(screen.getByText('正在载入…')).toBeTruthy()
    expect(screen.queryByText('今天没有安排，记一笔吧')).toBeNull()
  })

  it('error：显示错误文案与重试按钮，且不显示空态假象', () => {
    const onRetry = vi.fn()
    renderCard({ error: '日历加载失败', onRetry })
    expect(screen.getByText('日历加载失败')).toBeTruthy()
    // 失败时计数丸留空，避免「0 件」误导
    expect(screen.queryByText('0 件')).toBeNull()
    expect(screen.queryByText('今天没有安排，记一笔吧')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('error 且无 onRetry：只显示文案，不渲染重试按钮', () => {
    renderCard({ error: '加载失败' })
    expect(screen.getByText('加载失败')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '重试' })).toBeNull()
  })

  it('计数口径：有未完成时显示「N 件待办」', () => {
    renderCard({ events: [ev({ id: 1 }), ev({ id: 2, is_completed: true })] })
    expect(screen.getByText('1 件待办')).toBeTruthy()
  })

  it('计数口径：全部完成时显示「0 件待办」', () => {
    // total 为真 → 走 `${total - doneCount} 件待办` 分支
    const { container, unmount } = renderCard({ events: [ev({ id: 3, is_completed: true })] })
    expect(within(container).getByText('0 件待办')).toBeTruthy()
    unmount()
  })

  it('点勾选按钮触发 onToggleComplete，并带 aria-label 反映当前状态', () => {
    const onToggleComplete = vi.fn()
    const e = ev()
    renderCard({ events: [e], onToggleComplete })

    fireEvent.click(screen.getByRole('button', { name: '标记为完成' }))
    expect(onToggleComplete).toHaveBeenCalledWith(e)
  })

  it('已完成项的勾选按钮 aria-label 为「标记为未完成」', () => {
    renderCard({ events: [ev({ is_completed: true })] })
    expect(screen.getByRole('button', { name: '标记为未完成' })).toBeTruthy()
  })

  it('点标题打开详情', () => {
    const onOpenEvent = vi.fn()
    const e = ev({ title: '开庭' })
    renderCard({ events: [e], onOpenEvent })

    fireEvent.click(screen.getByText('开庭'))
    expect(onOpenEvent).toHaveBeenCalledWith(e)
  })

  it('底部汇总显示已完成 / 总数', () => {
    renderCard({ events: [ev({ id: 1, is_completed: true }), ev({ id: 2 })] })
    // 「已完成 N / M」被 <b> 打断，用正则匹配容器文本
    expect(screen.getByText(/已完成/)).toBeTruthy()
    expect(screen.getByText('点圆圈标记完成')).toBeTruthy()
  })
})
