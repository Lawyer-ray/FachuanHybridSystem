// @vitest-environment jsdom
/**
 * DealRow 渲染与交互测试（jsdom）。
 *
 * 交互语义是本组件的核心约定：
 * - 左键行 / Enter / Space → 详情页（onOpenDetail）
 * - 右键行 / 👁 按钮 → 抽屉预览（onOpenSheet）
 * - 行内按钮自身可激活，按键与点击都不能重复触发行级动作
 * - data-prev 元素上的点击不触发行级 left-click
 *
 * 视觉分支：今日到期红点脉冲、ctype 标签、vs 对方、金额与到期文案。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../domain', () => ({
  relDue: (n: number) => (n === 0 ? '今日到期' : n < 0 ? `已到期 ${-n} 天` : `剩 ${n} 天`),
}))

import { DealRow } from './DealRow'
import type { WorkbenchDeal } from '../types'

function deal(over: Partial<WorkbenchDeal> = {}): WorkbenchDeal {
  return {
    id: 7,
    client: '张三诉李四买卖合同纠纷',
    ctype: '民商事',
    lit: true,
    parties: { client: '张三', other: '李四' },
    no: '（20XX）京01民初1号',
    amount: '¥100,000',
    daysLeft: 3,
    ...over,
  } as unknown as WorkbenchDeal
}

function renderRow(props: Partial<Parameters<typeof DealRow>[0]> = {}) {
  const onOpenSheet = vi.fn()
  const onOpenDetail = vi.fn()
  const utils = render(
    <DealRow deal={deal()} onOpenSheet={onOpenSheet} onOpenDetail={onOpenDetail} {...props} />,
  )
  const row = utils.container.querySelector('[data-deal-id]') as HTMLElement
  return { ...utils, row, onOpenSheet, onOpenDetail }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('DealRow：渲染', () => {
  it('渲染客户名、类型标签、双方、案号', () => {
    const { container } = renderRow()
    expect(container.textContent).toContain('张三诉李四买卖合同纠纷')
    expect(container.textContent).toContain('民商事')
    expect(container.textContent).toContain('张三')
    expect(container.textContent).toContain('vs')
    expect(container.textContent).toContain('李四')
    expect(container.textContent).toContain('（20XX）京01民初1号')
    container.remove()
  })

  it('渲染金额与到期文案', () => {
    const { container } = renderRow({ deal: deal({ amount: '¥50,000', daysLeft: 5 }) })
    expect(container.textContent).toContain('¥50,000')
    expect(container.textContent).toContain('剩 5 天')
    container.remove()
  })

  it('无 ctype 时不渲染类型标签', () => {
    const { container } = renderRow({ deal: deal({ ctype: null as never }) })
    expect(container.textContent).not.toContain('民商事')
    container.remove()
  })

  it('无对方时只显示我方，不出现 vs', () => {
    const { container } = renderRow({ deal: deal({ parties: { client: '张三', other: '' } as never }) })
    expect(container.textContent).not.toContain('vs')
    container.remove()
  })

  it('无金额时金额行不渲染', () => {
    const { container } = renderRow({ deal: deal({ amount: null as never }) })
    expect(container.textContent).not.toContain('¥')
    container.remove()
  })

  it('daysLeft 为 null 时不渲染到期文案', () => {
    const { container } = renderRow({ deal: deal({ daysLeft: null }) })
    expect(container.textContent).not.toContain('剩')
    expect(container.textContent).not.toContain('已到期')
    container.remove()
  })

  it('今日到期：行加 today 类且文案为「今日到期」', () => {
    const { container, row } = renderRow({ deal: deal({ daysLeft: 0 }) })
    expect(row.className).toContain('today')
    expect(container.textContent).toContain('今日到期')
    container.remove()
  })

  it('非今日不加 today 类', () => {
    const { row, unmount } = renderRow({ deal: deal({ daysLeft: 3 }) })
    expect(row.className).not.toContain('today')
    unmount()
  })

  it('逾期显示「已到期 N 天」', () => {
    const { container } = renderRow({ deal: deal({ daysLeft: -2 }) })
    expect(container.textContent).toContain('已到期 2 天')
    container.remove()
  })
})

describe('DealRow：左键与键盘进详情', () => {
  it('左键行触发 onOpenDetail', () => {
    const { row, onOpenDetail, onOpenSheet, unmount } = renderRow()
    fireEvent.click(row)
    expect(onOpenDetail).toHaveBeenCalledWith(expect.objectContaining({ id: 7 }))
    expect(onOpenSheet).not.toHaveBeenCalled()
    unmount()
  })

  it('Enter 触发 onOpenDetail', () => {
    const { row, onOpenDetail, unmount } = renderRow()
    fireEvent.keyDown(row, { key: 'Enter' })
    expect(onOpenDetail).toHaveBeenCalled()
    unmount()
  })

  it('Space 触发 onOpenDetail', () => {
    const { row, onOpenDetail, unmount } = renderRow()
    fireEvent.keyDown(row, { key: ' ' })
    expect(onOpenDetail).toHaveBeenCalled()
    unmount()
  })

  it('其他键不触发', () => {
    const { row, onOpenDetail, unmount } = renderRow()
    fireEvent.keyDown(row, { key: 'a' })
    expect(onOpenDetail).not.toHaveBeenCalled()
    unmount()
  })

  it('行内按钮上的键盘事件不重复触发行级动作', () => {
    const { onOpenDetail, unmount } = renderRow()
    const btn = screen.getByRole('button', { name: '快速预览' })
    fireEvent.keyDown(btn, { key: 'Enter' })
    expect(onOpenDetail).not.toHaveBeenCalled()
    unmount()
  })

  it('点 data-prev 区域不触发行级 left-click', () => {
    const { onOpenDetail, unmount } = renderRow()
    const prevBtn = screen.getByRole('button', { name: '快速预览' })
    fireEvent.click(prevBtn)
    expect(onOpenDetail).not.toHaveBeenCalled()
    unmount()
  })
})

describe('DealRow：右键与按钮开抽屉', () => {
  it('右键行触发 onOpenSheet 且阻止默认菜单', () => {
    const { row, onOpenSheet, unmount } = renderRow()
    const e = fireEvent.contextMenu(row)
    expect(onOpenSheet).toHaveBeenCalledWith(expect.objectContaining({ id: 7 }))
    expect(e).toBe(false) // preventDefault → fireEvent 返回 false
    unmount()
  })

  it('点 👁 快速预览触发 onOpenSheet', () => {
    const { onOpenSheet, onOpenDetail, unmount } = renderRow()
    fireEvent.click(screen.getByRole('button', { name: '快速预览' }))
    expect(onOpenSheet).toHaveBeenCalled()
    expect(onOpenDetail).not.toHaveBeenCalled()
    unmount()
  })

  it('点 → 打开详情触发 onOpenDetail', () => {
    const { onOpenDetail, onOpenSheet, unmount } = renderRow()
    fireEvent.click(screen.getByRole('button', { name: '打开详情' }))
    expect(onOpenDetail).toHaveBeenCalled()
    expect(onOpenSheet).not.toHaveBeenCalled()
    unmount()
  })

  it('非诉案件的详情按钮 title 标明开发中', () => {
    const { unmount } = renderRow({ deal: deal({ lit: false }) })
    expect(screen.getByRole('button', { name: '打开详情' }).getAttribute('title')).toContain('开发中')
    unmount()
  })
})
