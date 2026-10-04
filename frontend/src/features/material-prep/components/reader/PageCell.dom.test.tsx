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
import { fireEvent, render } from '@testing-library/react'
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
