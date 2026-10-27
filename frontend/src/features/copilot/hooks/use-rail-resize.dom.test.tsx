// @vitest-environment jsdom
/**
 * useRailResize 测试（jsdom）。
 *
 * 核心不变量：
 * - 宽度钳制在 [MIN_WIDTH, 面板宽 - CHAT_MIN]；panelWidth 未知（0）时不钳上限
 * - 拖动中直改 rail 的 `--copilot-rail-w` CSS 变量、不触发 React 重渲染；
 *   松手才提交 state 并持久化
 * - 只响应主键（button === 0）
 * - pointercancel 与 pointerup 等价收尾，userSelect 复原值而非清空
 *
 * 「pointercancel」这条是本次修的缺陷：触摸/笔被系统手势打断时浏览器只发
 * pointercancel，漏掉它则 userSelect: none 永久残留、整页选不中文字。
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { useRailResize } from './use-rail-resize'

const RAIL_WIDTH_KEY = 'copilot:rail-width'
const PANEL_WIDTH = 800

function pointer(type: string, clientX: number, button = 0) {
  const e = new Event(type, { bubbles: true, cancelable: true }) as Event & {
    clientX?: number
    button?: number
  }
  e.clientX = clientX
  e.button = button
  return e
}

beforeEach(() => {
  localStorage.clear()
  document.body.style.userSelect = ''
  document.body.style.cursor = ''
})

afterEach(() => {
  document.body.style.userSelect = ''
  document.body.style.cursor = ''
})

describe('useRailResize：初始宽度', () => {
  it('无记忆时用默认 220', () => {
    const { result } = renderHook(() => useRailResize(PANEL_WIDTH))
    expect(result.current.width).toBe(220)
  })

  it('合法记忆值沿用', () => {
    localStorage.setItem(RAIL_WIDTH_KEY, '300')
    const { result } = renderHook(() => useRailResize(PANEL_WIDTH))
    expect(result.current.width).toBe(300)
  })

  it('低于下限的记忆值回落默认', () => {
    localStorage.setItem(RAIL_WIDTH_KEY, '100')
    const { result } = renderHook(() => useRailResize(PANEL_WIDTH))
    expect(result.current.width).toBe(220)
  })

  it('记忆值非数字回落默认', () => {
    localStorage.setItem(RAIL_WIDTH_KEY, 'abc')
    const { result } = renderHook(() => useRailResize(PANEL_WIDTH))
    expect(result.current.width).toBe(220)
  })

  it('超过「面板宽 - 对话区最小宽」的记忆值被钳制', () => {
    // 上限 = 800 - 280 = 520
    localStorage.setItem(RAIL_WIDTH_KEY, '900')
    const { result } = renderHook(() => useRailResize(PANEL_WIDTH))
    expect(result.current.width).toBe(520)
  })

  it('panelWidth 未知（0）时不钳上限（单测直接渲染侧栏的场景）', () => {
    localStorage.setItem(RAIL_WIDTH_KEY, '900')
    const { result } = renderHook(() => useRailResize(0))
    expect(result.current.width).toBe(900)
  })
})

describe('useRailResize：拖拽', () => {
  it('非主键按下不启动拖拽', () => {
    const { result } = renderHook(() => useRailResize(PANEL_WIDTH))
    act(() => {
      result.current.onHandlePointerDown(pointer('pointerdown', 100, 2) as never)
    })
    expect(document.body.style.userSelect).toBe('')
    expect(document.body.style.cursor).toBe('')
  })

  it('拖动中直改 CSS 变量，松手才提交 state 并持久化', () => {
    const { result } = renderHook(() => useRailResize(PANEL_WIDTH))
    const node = document.createElement('div')
    document.body.appendChild(node)
    act(() => {
      result.current.setRailRef(node)
    })

    act(() => {
      result.current.onHandlePointerDown(pointer('pointerdown', 100) as never)
    })
    expect(document.body.style.userSelect).toBe('none')
    expect(document.body.style.cursor).toBe('col-resize')

    // 侧栏在左，向右拖 100px → 220 + 100 = 320
    act(() => {
      window.dispatchEvent(pointer('pointermove', 200))
    })
    expect(node.style.getPropertyValue('--copilot-rail-w')).toBe('320px')
    // 此时 state 尚未提交
    expect(result.current.width).toBe(220)

    act(() => {
      window.dispatchEvent(pointer('pointerup', 200))
    })
    expect(result.current.width).toBe(320)
    expect(localStorage.getItem(RAIL_WIDTH_KEY)).toBe('320')
    expect(document.body.style.userSelect).toBe('')
    expect(document.body.style.cursor).toBe('')
    node.remove()
  })

  it('向左拖变窄，但不低于最小宽度', () => {
    const { result } = renderHook(() => useRailResize(PANEL_WIDTH))
    act(() => {
      result.current.onHandlePointerDown(pointer('pointerdown', 500) as never)
    })
    act(() => {
      window.dispatchEvent(pointer('pointermove', -5000))
    })
    act(() => {
      window.dispatchEvent(pointer('pointerup', -5000))
    })
    expect(result.current.width).toBe(180)
  })

  it('pointercancel 也收尾：提交宽度并复位样式（触摸被系统手势打断）', () => {
    const { result } = renderHook(() => useRailResize(PANEL_WIDTH))
    const node = document.createElement('div')
    document.body.appendChild(node)
    act(() => {
      result.current.setRailRef(node)
    })

    act(() => {
      result.current.onHandlePointerDown(pointer('pointerdown', 100) as never)
    })
    act(() => {
      window.dispatchEvent(pointer('pointermove', 200))
    })

    act(() => {
      window.dispatchEvent(pointer('pointercancel', 200))
    })
    expect(result.current.width).toBe(320)
    expect(document.body.style.userSelect).toBe('')
    expect(document.body.style.cursor).toBe('')
    node.remove()
  })

  it('拖拽结束把 userSelect 还原成原值而不是清空', () => {
    document.body.style.userSelect = 'text'
    const { result } = renderHook(() => useRailResize(PANEL_WIDTH))

    act(() => {
      result.current.onHandlePointerDown(pointer('pointerdown', 100) as never)
    })
    expect(document.body.style.userSelect).toBe('none')

    act(() => {
      window.dispatchEvent(pointer('pointerup', 100))
    })
    expect(document.body.style.userSelect).toBe('text')
  })

  it('卸载时收尾进行中的拖拽：userSelect 不残留', () => {
    const { result, unmount } = renderHook(() => useRailResize(PANEL_WIDTH))
    act(() => {
      result.current.onHandlePointerDown(pointer('pointerdown', 100) as never)
    })
    expect(document.body.style.userSelect).toBe('none')

    unmount()
    expect(document.body.style.userSelect).toBe('')
    expect(document.body.style.cursor).toBe('')
  })

  it('未移动直接松手：不写 localStorage', () => {
    const { result } = renderHook(() => useRailResize(PANEL_WIDTH))
    act(() => {
      result.current.onHandlePointerDown(pointer('pointerdown', 100) as never)
    })
    act(() => {
      window.dispatchEvent(pointer('pointerup', 100))
    })
    expect(localStorage.getItem(RAIL_WIDTH_KEY)).toBeNull()
  })
})
