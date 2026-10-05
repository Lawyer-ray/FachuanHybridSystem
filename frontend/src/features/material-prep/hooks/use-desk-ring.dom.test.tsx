// @vitest-environment jsdom
/**
 * useDeskRing 单测（jsdom）。
 *
 * 高亮框直接 DOM 绘制（ref + rAF，绕过 React 协调）。用真实 div 挂
 * wrap/grid/ring 与 data-pack-idx 卡片，getBoundingClientRect 逐元素覆写，
 * 断言 ring 的 class/尺寸/transform 跟随选中卡片、无卡片时熄灭、
 * sel 越界钳到最后一张、scroll 触发同步重绘。
 */
import { useRef } from 'react'
import { render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { InboxMessage } from '../types'
import { useDeskRing } from './use-desk-ring'

const roSpy = { disconnect: vi.fn(), observe: vi.fn() }

beforeEach(() => {
  roSpy.disconnect.mockClear()
  roSpy.observe.mockClear()
  // jsdom 无 ResizeObserver：hook 挂载时要 observe(grid)
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe = roSpy.observe
      disconnect = roSpy.disconnect
    },
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function rectOf(left: number, top: number, width: number, height: number): DOMRect {
  return { left, top, width, height, right: left + width, bottom: top + height } as DOMRect
}

/** 卡片 i 摆在 (i*100, 20)，90x50；wrap 在原点 */
function stubRects(wrap: HTMLElement, grid: HTMLElement, cards: HTMLElement[]) {
  wrap.getBoundingClientRect = () => rectOf(0, 0, 600, 400)
  grid.getBoundingClientRect = () => rectOf(0, 0, 600, 300)
  cards.forEach((c, i) => {
    c.getBoundingClientRect = () => rectOf(i * 100, 20, 90, 50)
  })
}

function RingHarness({ sel, count }: { sel: number; count: number }) {
  const gridRef = useRef<HTMLDivElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const ringRef = useRef<HTMLDivElement>(null)
  useDeskRing({
    sel,
    visible: Array.from({ length: count }, (_, i) => ({ id: i }) as InboxMessage),
    tab: 'todo',
    gridRef,
    wrapRef,
    ringRef,
  })
  return (
    <div ref={wrapRef}>
      <div ref={gridRef}>
        {Array.from({ length: count }, (_, i) => (
          <div key={i} data-pack-idx={i} />
        ))}
      </div>
      <div ref={ringRef} />
    </div>
  )
}

/** 等 rAF 落帧 */
const nextFrame = () => new Promise<void>((r) => requestAnimationFrame(() => r()))

function refsOf(container: HTMLElement) {
  const wrap = container.firstElementChild as HTMLDivElement
  const grid = wrap.firstElementChild as HTMLDivElement
  const ring = wrap.lastElementChild as HTMLDivElement
  return { grid, wrap, ring }
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('useDeskRing', () => {
  it('选中卡片：ring 点亮并对齐其盒（宽高 + 相对 wrap 的位移）', async () => {
    const { container } = render(<RingHarness sel={1} count={3} />)
    const { grid, wrap, ring } = refsOf(container)
    stubRects(wrap, grid, Array.from(grid.querySelectorAll('[data-pack-idx]')))
    // 挂载后的首帧由 rAF 驱动；refs 覆写晚于首帧，触发一次 scroll 重绘
    await nextFrame()
    window.dispatchEvent(new Event('scroll'))

    expect(ring.classList.contains('on')).toBe(true)
    expect(ring.style.width).toBe('90px')
    expect(ring.style.height).toBe('50px')
    // 卡片1 left=100、top=20（wrap 原点）
    expect(ring.style.transform).toBe('translate(100px, 20px)')
  })

  it('sel 越界：钳到最后一张卡', async () => {
    const { container } = render(<RingHarness sel={99} count={2} />)
    const { grid, wrap, ring } = refsOf(container)
    stubRects(wrap, grid, Array.from(grid.querySelectorAll('[data-pack-idx]')))
    await nextFrame()
    window.dispatchEvent(new Event('scroll'))
    expect(ring.style.transform).toBe('translate(100px, 20px)')
  })

  it('无卡片：ring 熄灭（on 移除）', async () => {
    const { container, rerender } = render(<RingHarness sel={0} count={1} />)
    const { grid, wrap, ring } = refsOf(container)
    stubRects(wrap, grid, Array.from(grid.querySelectorAll('[data-pack-idx]')))
    await nextFrame()
    window.dispatchEvent(new Event('scroll'))
    expect(ring.classList.contains('on')).toBe(true)

    rerender(<RingHarness sel={0} count={0} />)
    await nextFrame()
    // 熄灭走 class 移除（内联样式残留无碍——.on 才控制可见性）
    expect(ring.classList.contains('on')).toBe(false)
  })

  it('sel 变化（不换订阅）触发重绘对齐新卡', async () => {
    const { container, rerender } = render(<RingHarness sel={0} count={3} />)
    const { grid, wrap, ring } = refsOf(container)
    stubRects(wrap, grid, Array.from(grid.querySelectorAll('[data-pack-idx]')))
    await nextFrame()
    window.dispatchEvent(new Event('scroll'))
    expect(ring.style.transform).toBe('translate(0px, 20px)')

    rerender(<RingHarness sel={2} count={3} />)
    await nextFrame()
    expect(ring.style.transform).toBe('translate(200px, 20px)')
  })

  it('挂载即观察 grid；卸载断开 ResizeObserver（scroll/resize 订阅拆除）', async () => {
    const { container, unmount } = render(<RingHarness sel={0} count={1} />)
    const { grid, wrap, ring } = refsOf(container)
    stubRects(wrap, grid, Array.from(grid.querySelectorAll('[data-pack-idx]')))
    await nextFrame()
    window.dispatchEvent(new Event('scroll'))
    expect(ring.classList.contains('on')).toBe(true)
    expect(roSpy.observe).toHaveBeenCalledWith(grid)

    unmount()
    expect(roSpy.disconnect).toHaveBeenCalled()
    // 卸载后事件不再驱动 ring（元素已脱离文档，监听器应已拆除）
    window.dispatchEvent(new Event('scroll'))
    window.dispatchEvent(new Event('resize'))
  })
})
