// @vitest-environment jsdom
/**
 * PageCell 取字模式 pointer 交互单测（jsdom）。
 *
 * 回归背景：阈值内（1px~MIN_DRAG）微位移曾让 pointerup 既不触发 onOcrBox
 * 也不触发 onPickPage（点击死区）。判定收敛到 resolveDragRect 后：
 * 阈值内位移 → onPickPage 记页码；超阈值拖框 → onOcrBox 框选。
 *
 * 页体渲染分支（Pdf/PhotoPageView）mock 成空组件，只测 pointer 分派契约。
 */
import { act, fireEvent, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./PdfPageView', () => ({ PdfPageView: () => null }))
vi.mock('./PhotoPageView', () => ({ PhotoPageView: () => null }))

import { PageCell } from './PageCell'
import type { BundleMat } from '../../types'

const mat: BundleMat = { partIndex: 0, n: '证据.docx', k: 'office', pages: 3 }

beforeEach(() => {
  // jsdom 的 getBoundingClientRect 恒零：钉一张 1000x1000 的版面，clientX/Y 可直接换算归一化坐标
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
    x: 0,
    y: 0,
    top: 0,
    left: 0,
    right: 1000,
    bottom: 1000,
    width: 1000,
    height: 1000,
    toJSON: () => ({}),
  } as DOMRect)
})

afterEach(() => {
  vi.restoreAllMocks()
})

/** jsdom 无 PointerEvent：用 MouseEvent 携带 clientX/Y 与 button 派发 pointer 系事件 */
function pointer(type: 'pointerdown' | 'pointermove' | 'pointerup', x: number, y: number) {
  return new MouseEvent(type, { bubbles: true, cancelable: true, button: 0, clientX: x, clientY: y })
}

function cellEl(container: HTMLElement): HTMLElement {
  return container.firstElementChild as HTMLElement
}

describe('PageCell 取字拖框分派', () => {
  it('纯点击无位移：onPickPage 记页码', () => {
    const onPickPage = vi.fn()
    const onOcrBox = vi.fn()
    const { container } = render(
      <PageCell messageId={1} mi={0} p={2} mat={mat} pickActive onPickPage={onPickPage} onOcrBox={onOcrBox} />,
    )
    const el = cellEl(container)
    fireEvent(el, pointer('pointerdown', 500, 500))
    fireEvent(el, pointer('pointerup', 500, 500))
    expect(onPickPage).toHaveBeenCalledWith(0, 2)
    expect(onOcrBox).not.toHaveBeenCalled()
  })

  it('阈值内微位移（0.5%）：仍走 onPickPage —— 修复前的点击死区', () => {
    const onPickPage = vi.fn()
    const onOcrBox = vi.fn()
    const { container } = render(
      <PageCell messageId={1} mi={0} p={2} mat={mat} pickActive onPickPage={onPickPage} onOcrBox={onOcrBox} />,
    )
    const el = cellEl(container)
    fireEvent(el, pointer('pointerdown', 500, 500))
    fireEvent(el, pointer('pointermove', 505, 500)) // 5/1000 = 0.5% < MIN_DRAG(1.8%)
    fireEvent(el, pointer('pointerup', 505, 500))
    expect(onPickPage).toHaveBeenCalledWith(0, 2)
    expect(onOcrBox).not.toHaveBeenCalled()
  })

  it('超阈值拖框：走 onOcrBox，携带归一化矩形', () => {
    const onPickPage = vi.fn()
    const onOcrBox = vi.fn()
    const { container } = render(
      <PageCell messageId={1} mi={0} p={2} mat={mat} pickActive onPickPage={onPickPage} onOcrBox={onOcrBox} />,
    )
    const el = cellEl(container)
    // 250/1000 → 500/1000：横纵各 25%，二进制精确值，矩形断言无浮点噪声
    fireEvent(el, pointer('pointerdown', 250, 500))
    fireEvent(el, pointer('pointermove', 500, 750))
    fireEvent(el, pointer('pointerup', 500, 750))
    expect(onOcrBox).toHaveBeenCalledWith(0, 2, { x: 0.25, y: 0.5, w: 0.25, h: 0.25 })
    expect(onPickPage).not.toHaveBeenCalled()
  })

  it('非取字模式：pointer 交互不触发任何回调', () => {
    const onPickPage = vi.fn()
    const onOcrBox = vi.fn()
    const { container } = render(
      <PageCell messageId={1} mi={0} p={2} mat={mat} onPickPage={onPickPage} onOcrBox={onOcrBox} />,
    )
    const el = cellEl(container)
    fireEvent(el, pointer('pointerdown', 500, 500))
    fireEvent(el, pointer('pointermove', 550, 520))
    fireEvent(el, pointer('pointerup', 550, 520))
    expect(onPickPage).not.toHaveBeenCalled()
    expect(onOcrBox).not.toHaveBeenCalled()
  })
})

// ============ 选页模式 / 点击分派 / 标记渲染 / 懒加载（2026-10 覆盖率补测） ============

describe('PageCell 选页模式', () => {
  it('选页模式：整页可点选并有 button 语义与 aria-pressed', () => {
    const onToggleSel = vi.fn()
    const { container } = render(
      <PageCell messageId={1} mi={0} p={2} mat={mat} selModeActive selected={false} onToggleSel={onToggleSel} />,
    )
    const el = cellEl(container)
    expect(el.getAttribute('role')).toBe('button')
    expect(el.getAttribute('tabindex')).toBe('0')
    expect(el.getAttribute('aria-pressed')).toBe('false')
  })

  it('已选中时 aria-pressed 为 true 并显示勾选角标', () => {
    const { container } = render(
      <PageCell messageId={1} mi={0} p={2} mat={mat} selModeActive selected onToggleSel={vi.fn()} />,
    )
    expect(cellEl(container).getAttribute('aria-pressed')).toBe('true')
    expect(container.textContent).toContain('✓')
  })

  it('Enter 键切换选中（shiftKey=false）', () => {
    const onToggleSel = vi.fn()
    const { container } = render(
      <PageCell messageId={1} mi={0} p={2} mat={mat} selModeActive selected={false} onToggleSel={onToggleSel} />,
    )
    fireEvent.keyDown(cellEl(container), { key: 'Enter' })
    expect(onToggleSel).toHaveBeenCalledWith(0, 2, false)
  })

  it('空格键同样切换选中', () => {
    const onToggleSel = vi.fn()
    const { container } = render(
      <PageCell messageId={1} mi={0} p={2} mat={mat} selModeActive selected={false} onToggleSel={onToggleSel} />,
    )
    fireEvent.keyDown(cellEl(container), { key: ' ' })
    expect(onToggleSel).toHaveBeenCalledWith(0, 2, false)
  })

  it('其他键不触发切换', () => {
    const onToggleSel = vi.fn()
    const { container } = render(
      <PageCell messageId={1} mi={0} p={2} mat={mat} selModeActive selected={false} onToggleSel={onToggleSel} />,
    )
    fireEvent.keyDown(cellEl(container), { key: 'a' })
    expect(onToggleSel).not.toHaveBeenCalled()
  })

  it('非选页模式无 button 语义（不进 tab 序）', () => {
    const { container } = render(<PageCell messageId={1} mi={0} p={2} mat={mat} />)
    const el = cellEl(container)
    expect(el.getAttribute('role')).toBeNull()
    expect(el.getAttribute('tabindex')).toBeNull()
  })
})

describe('PageCell 点击分派', () => {
  it('⌘ 点击走选页切换', () => {
    const onToggleSel = vi.fn()
    const { container } = render(<PageCell messageId={1} mi={0} p={2} mat={mat} onToggleSel={onToggleSel} />)
    fireEvent.click(cellEl(container), { metaKey: true })
    expect(onToggleSel).toHaveBeenCalledWith(0, 2, false)
  })

  it('⇧ 点击带 shiftKey=true 下发（用于区间选）', () => {
    const onToggleSel = vi.fn()
    const { container } = render(<PageCell messageId={1} mi={0} p={2} mat={mat} onToggleSel={onToggleSel} />)
    fireEvent.click(cellEl(container), { shiftKey: true })
    expect(onToggleSel).toHaveBeenCalledWith(0, 2, true)
  })

  it('取字模式下普通点击不触发选页（避免与框选冲突）', () => {
    const onToggleSel = vi.fn()
    const { container } = render(
      <PageCell messageId={1} mi={0} p={2} mat={mat} pickActive onToggleSel={onToggleSel} />,
    )
    fireEvent.click(cellEl(container), { metaKey: true })
    expect(onToggleSel).not.toHaveBeenCalled()
  })

  it('拖框后（movedRef=true）的 click 不再切换选中', () => {
    const onToggleSel = vi.fn()
    const { container } = render(
      <PageCell messageId={1} mi={0} p={2} mat={mat} pickActive onToggleSel={onToggleSel} onOcrBox={vi.fn()} />,
    )
    const el = cellEl(container)
    fireEvent(el, pointer('pointerdown', 250, 500))
    fireEvent(el, pointer('pointermove', 500, 750))
    fireEvent(el, pointer('pointerup', 500, 750))
    fireEvent.click(el, { metaKey: true })
    expect(onToggleSel).not.toHaveBeenCalled()
  })
})

describe('PageCell 上下文菜单与页脚', () => {
  it('右键触发 onContextMenu 并带坐标', () => {
    const onContextMenu = vi.fn()
    const { container } = render(
      <PageCell messageId={1} mi={0} p={2} mat={mat} onContextMenu={onContextMenu} />,
    )
    fireEvent.contextMenu(cellEl(container), { clientX: 10, clientY: 20 })
    expect(onContextMenu).toHaveBeenCalledWith(expect.anything(), 0, 2)
  })

  it('页脚显示页码 / 总页数', () => {
    const { container } = render(<PageCell messageId={1} mi={0} p={2} mat={mat} />)
    expect(container.textContent).toContain('2 / 3')
  })

  it('页脚按 hideMatName 决定是否显示源文件名（占位层文案不受其影响）', () => {
    // 页脚是最后一个 flex 容器里的 truncate span；用其文本判定，避免与
    // OfficePlaceholder 内部说明文案里的文件名混淆
    const footerOf = (c: HTMLElement) => c.querySelector('.flex.items-center.justify-between')?.textContent ?? ''

    const shown = render(<PageCell messageId={1} mi={0} p={2} mat={mat} />)
    expect(footerOf(shown.container)).toContain('证据.docx')
    shown.unmount()

    const hidden = render(<PageCell messageId={1} mi={0} p={2} mat={mat} hideMatName />)
    expect(footerOf(hidden.container)).not.toContain('证据.docx')
    hidden.unmount()
  })
})

describe('PageCell 标记渲染', () => {
  it('marks 渲染绿框与字段名标签', () => {
    const marks = [{ fi: 0, rect: { x: 0.1, y: 0.2, w: 0.3, h: 0.4 }, label: '标的额' }]
    const { container } = render(<PageCell messageId={1} mi={0} p={2} mat={mat} marks={marks} />)
    expect(container.textContent).toContain('标的额')
  })

  it('ocrRect 渲染待确认框', () => {
    const { container } = render(
      <PageCell messageId={1} mi={0} p={2} mat={mat} ocrRect={{ x: 0.1, y: 0.1, w: 0.2, h: 0.2 }} />,
    )
    // 待确认框是绝对定位 div，靠 border 类识别
    expect(container.querySelectorAll('.border-green-500').length).toBeGreaterThan(0)
  })
})

describe('PageCell 页体懒加载', () => {
  it('无 IntersectionObserver 时直接渲染页体（退化旧行为）', () => {
    const original = globalThis.IntersectionObserver
    // @ts-expect-error 故意移除以验证退化分支
    delete globalThis.IntersectionObserver

    const { container } = render(<PageCell messageId={1} mi={0} p={2} mat={mat} />)
    // office 类型 → OfficePlaceholder，渲染出占位文案而非骨架
    expect(container.textContent).toContain('2 / 3')
    globalThis.IntersectionObserver = original
  })

  it('视口外先挂骨架，进入视口后渲染页体', async () => {
    let cb: ((entries: Array<{ isIntersecting: boolean }>) => void) | null = null
    class FakeIO {
      constructor(f: (entries: Array<{ isIntersecting: boolean }>) => void) {
        cb = f
      }
      observe() {}
      disconnect() {}
    }
    const original = globalThis.IntersectionObserver
    ;(globalThis as unknown as { IntersectionObserver: unknown }).IntersectionObserver = FakeIO

    const { container } = render(<PageCell messageId={1} mi={0} p={2} mat={mat} />)
    // 未进入视口：页脚仍在（PageCell 外框），但页体是骨架
    expect(container.textContent).toContain('2 / 3')

    await act(async () => {
      cb?.([{ isIntersecting: true }])
      await Promise.resolve()
    })
    expect(container.textContent).toContain('2 / 3')
    globalThis.IntersectionObserver = original
  })
})
