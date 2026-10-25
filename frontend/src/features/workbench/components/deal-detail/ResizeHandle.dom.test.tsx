// @vitest-environment jsdom
/**
 * ResizeHandle 测试。
 *
 * 上一版的真实故障：handle 用 `-mx-[4px]` 让 9px 命中区探进两侧栏，但左侧是
 * `flex-1` 的邻居、DOM 又在前，绘制层叠在上 → 探进去的那 4px 被盖住，点不到、
 * 拖不动。所以这里除了交互本身，还要断言它**在布局里真实占位**（不靠负边距），
 * 否则同样的坑会再踩一次。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ResizeHandle } from './ResizeHandle'

function setup(over: Partial<Parameters<typeof ResizeHandle>[0]> = {}) {
  const onPointerDown = vi.fn()
  const onKeyAdjust = vi.fn()
  render(
    <ResizeHandle dragging={false} onPointerDown={onPointerDown} onKeyAdjust={onKeyAdjust} {...over} />,
  )
  return { onPointerDown, onKeyAdjust }
}

describe('ResizeHandle', () => {
  it('暴露 separator 语义（键盘/读屏可发现）', () => {
    setup()
    const el = screen.getByRole('separator')
    expect(el.getAttribute('aria-orientation')).toBe('vertical')
    expect(el.tabIndex).toBe(0)
  })

  it('在布局里真实占位，不靠负边距', () => {
    // 负边距会让相邻 flex-1 栏盖住探进去的部分（上一版拖不动的根因）
    setup()
    const cls = screen.getByRole('separator').className
    expect(cls).toMatch(/w-\[10px\]/)
    expect(cls).not.toMatch(/-mx-/)
    // z-10：即便兄弟有背景色也压不住它
    expect(cls).toMatch(/z-10/)
  })

  it('撑满父级行高（否则 items-start 的 flex 行里高度为 0，点不到）', () => {
    // 这是「拖不动」的第二个根因：父级 items-start，子项按内容高度排布，
    // 分隔条没有内容 → height 0。jsdom 不计算布局，只能断言撑高契约。
    setup()
    const el = screen.getByRole('separator')
    expect(el.className).toMatch(/self-stretch|h-full/)
    expect(el.className).toMatch(/min-h-\[/)
  })

  it('指针按下触发拖拽', () => {
    const { onPointerDown } = setup()
    fireEvent.pointerDown(screen.getByRole('separator'))
    expect(onPointerDown).toHaveBeenCalled()
  })

  it('← → 键调整宽度（不只鼠标能用）', () => {
    const { onKeyAdjust } = setup()
    const el = screen.getByRole('separator')
    fireEvent.keyDown(el, { key: 'ArrowLeft' })
    fireEvent.keyDown(el, { key: 'ArrowRight' })
    expect(onKeyAdjust).toHaveBeenNthCalledWith(1, -1)
    expect(onKeyAdjust).toHaveBeenNthCalledWith(2, 1)
  })

  it('拖拽中视觉加粗（给用户「正在拖」的反馈）', () => {
    setup({ dragging: true })
    const bar = screen.getByRole('separator').querySelector('span')
    expect(bar?.className).toMatch(/w-\[3px\]/)
    expect(bar?.className).toMatch(/bg-foreground/)
  })

  it('其余按键不干扰（不 preventDefault）', () => {
    const { onKeyAdjust } = setup()
    fireEvent.keyDown(screen.getByRole('separator'), { key: 'a' })
    expect(onKeyAdjust).not.toHaveBeenCalled()
  })
})
