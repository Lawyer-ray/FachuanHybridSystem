// @vitest-environment jsdom
/**
 * PanelBackdrop 单测（jsdom）。
 *
 * 这个遮罩的唯一职责是「面板展开时把背景压暗一档」，所以断言就盯三件事：
 * 1. 展开时节点在 DOM 里、带压暗背景色，收起时带淡出动画；
 * 2. 层级必须低于面板（z-[100]）——否则会把面板自己压暗；
 * 3. 点击遮罩要收起面板（吃掉指针事件，不能是 pointer-events-none）。
 *
 * 曾经踩过的坑（两个都直接表现为「丑」）：
 * 1. 早期版本把遮罩限制在 <1120px 断点下（min-[1120px]:hidden），宽屏并排
 *    dock 时背景一点不暗，用户直接反馈「背景没有变暗」。
 * 2. 后来用 inset-0 全屏压暗，把 sticky 的导航栏也盖成「置灰不可用」的
 *    样子（导航栏实际仍可点）。现在遮罩从 --app-navbar-h 起，只压内容区。
 * 这两条都写成断言，防它们再退化。
 */
import { fireEvent, render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { PanelBackdrop } from './PanelBackdrop'

function getBackdrop(container: HTMLElement) {
  const el = container.firstElementChild
  if (!el) throw new Error('遮罩未渲染')
  return el as HTMLElement
}

describe('PanelBackdrop', () => {
  it('展开时渲染并压暗背景', () => {
    const { container } = render(<PanelBackdrop open onClose={() => {}} />)
    const el = getBackdrop(container)
    expect(el.className).toContain('bg-black/')
    expect(el.className).toContain('fixed')
  })

  it('从导航栏下方开始压暗，不把常驻可点的顶栏一起置灰', () => {
    const { container } = render(<PanelBackdrop open onClose={() => {}} />)
    const cls = getBackdrop(container).className
    expect(cls).toContain('top-(--app-navbar-h)')
    // inset-0 会把 sticky 导航栏一起压暗（视觉禁用但其上的按钮仍可点）
    expect(cls).not.toMatch(/\binset-0\b/)
  })

  it('层级低于面板（z-[90] < z-[100]），避免把面板自己压暗', () => {
    const { container } = render(<PanelBackdrop open onClose={() => {}} />)
    expect(getBackdrop(container).className).toContain('z-[90]')
  })

  it('压暗强度对齐站内弹窗基线（bg-black/50）', () => {
    // 「新建日程」等弹窗走 shadcn Dialog，其遮罩就是 bg-black/50（见
    // components/ui/dialog.tsx）。不一致会让用户在不同层之间感到两种「暗」。
    const { container } = render(<PanelBackdrop open onClose={() => {}} />)
    expect(getBackdrop(container).className).toContain('bg-black/50')
  })

  it('不按视口隐藏：任何宽度下面板展开都压暗', () => {
    const { container } = render(<PanelBackdrop open onClose={() => {}} />)
    const cls = getBackdrop(container).className
    // 空字符串 class 也算隐患（Tailwind 语法错误时会静默失效）
    expect(cls).not.toMatch(/\bhidden\b/)
    expect(cls).not.toMatch(/min-\[|max-(sm|md|lg|xl)/)
  })

  it('展开播入场、收起播淡出', () => {
    const { container, rerender } = render(<PanelBackdrop open onClose={() => {}} />)
    expect(getBackdrop(container).className).toContain('animate-in')
    rerender(<PanelBackdrop open={false} onClose={() => {}} />)
    const cls = getBackdrop(container).className
    expect(cls).toContain('animate-out')
    expect(cls).toContain('fade-out')
  })

  it('点击遮罩收起面板', () => {
    const onClose = vi.fn()
    const { container } = render(<PanelBackdrop open onClose={onClose} />)
    fireEvent.click(getBackdrop(container))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('对读屏器隐藏（只是视觉层，不该被朗读）', () => {
    const { container } = render(<PanelBackdrop open onClose={() => {}} />)
    expect(getBackdrop(container).getAttribute('aria-hidden')).toBe('true')
  })
})
