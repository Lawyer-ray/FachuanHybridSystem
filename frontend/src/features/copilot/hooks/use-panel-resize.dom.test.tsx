// @vitest-environment jsdom
/**
 * usePanelResize 测试（jsdom）。
 *
 * 核心不变量：
 * - 宽度钳制在 [MIN_WIDTH, innerWidth-320]（窗口过窄时下限优先）
 * - localStorage 记忆值非法/读取抛错回落默认 600
 * - 拖动中直改 CSS 变量、不触发 React 重渲染；松手才提交 state 并持久化
 * - 只响应主键（button===0）
 * - railCapable = 视口够宽 && 宽度 >= 560
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { usePanelResize } from './use-panel-resize'

const WIDTH_KEY = 'copilot:width'

function setViewport(width: number) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: width })
}

/** 构造一个最小 PointerEvent（jsdom 无 PointerEvent 时退化） */
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
  setViewport(1440)
  document.body.style.userSelect = ''
})

afterEach(() => {
  setViewport(1440)
  document.body.style.userSelect = ''
})

describe('usePanelResize：初始宽度', () => {
  it('无记忆时用默认 600', () => {
    const { result } = renderHook(() => usePanelResize(true))
    expect(result.current.width).toBe(600)
  })

  it('合法记忆值沿用', () => {
    localStorage.setItem(WIDTH_KEY, '800')
    const { result } = renderHook(() => usePanelResize(true))
    expect(result.current.width).toBe(800)
  })

  it('记忆值超出上限时被钳制', () => {
    localStorage.setItem(WIDTH_KEY, '99999')
    const { result } = renderHook(() => usePanelResize(true))
    // 上限 = innerWidth - 320 = 1120
    expect(result.current.width).toBe(1120)
  })

  it('记忆值低于下限时钳制到最小宽度', () => {
    localStorage.setItem(WIDTH_KEY, '100')
    const { result } = renderHook(() => usePanelResize(true))
    expect(result.current.width).toBe(420)
  })

  it('记忆值非数字回落默认', () => {
    localStorage.setItem(WIDTH_KEY, 'abc')
    const { result } = renderHook(() => usePanelResize(true))
    expect(result.current.width).toBe(600)
  })

  it('窗口很窄时下限优先（不被上限压破）', () => {
    setViewport(500)
    localStorage.setItem(WIDTH_KEY, '600')
    const { result } = renderHook(() => usePanelResize(true))
    // max(MIN, 500-320=180) = 420 → 钳到 420
    expect(result.current.width).toBe(420)
  })
})

describe('usePanelResize：railCapable', () => {
  it('视口够宽且宽度达阈值时为 true', () => {
    localStorage.setItem(WIDTH_KEY, '600')
    const { result } = renderHook(() => usePanelResize(true))
    expect(result.current.railCapable).toBe(true)
  })

  it('宽度不足阈值时为 false', () => {
    localStorage.setItem(WIDTH_KEY, '500')
    const { result } = renderHook(() => usePanelResize(true))
    expect(result.current.railCapable).toBe(false)
  })

  it('视口不是 sm 以上时恒为 false', () => {
    localStorage.setItem(WIDTH_KEY, '1000')
    const { result } = renderHook(() => usePanelResize(false))
    expect(result.current.railCapable).toBe(false)
  })
})

describe('usePanelResize：拖拽', () => {
  it('非主键按下不启动拖拽', () => {
    const { result } = renderHook(() => usePanelResize(true))
    act(() => {
      result.current.onHandlePointerDown(pointer('pointerdown', 1000, 2) as never)
    })
    expect(document.body.style.userSelect).toBe('')
  })

  it('拖拽期间直改 CSS 变量，松手才提交 state', () => {
    const { result } = renderHook(() => usePanelResize(true))
    const node = document.createElement('aside')
    document.body.appendChild(node)
    act(() => {
      result.current.setPanelRef(node)
    })

    act(() => {
      result.current.onHandlePointerDown(pointer('pointerdown', 1000) as never)
    })
    expect(document.body.style.userSelect).toBe('none')

    // 向左拖 200px（面板锚定右侧，向左变宽）
    act(() => {
      window.dispatchEvent(pointer('pointermove', 800))
    })
    expect(node.style.getPropertyValue('--copilot-w')).toBe('800px')
    // 此时 state 尚未提交
    expect(result.current.width).toBe(600)

    act(() => {
      window.dispatchEvent(pointer('pointerup', 800))
    })
    expect(result.current.width).toBe(800)
    expect(document.body.style.userSelect).toBe('')
    expect(localStorage.getItem(WIDTH_KEY)).toBe('800')
    node.remove()
  })

  it('向右拖变窄，但不低于最小宽度', () => {
    const { result } = renderHook(() => usePanelResize(true))
    const node = document.createElement('aside')
    document.body.appendChild(node)
    act(() => {
      result.current.setPanelRef(node)
    })

    act(() => {
      result.current.onHandlePointerDown(pointer('pointerdown', 500) as never)
    })
    // 向右拖 500px → 目标 100，被钳到 420
    act(() => {
      window.dispatchEvent(pointer('pointermove', 1000))
    })
    act(() => {
      window.dispatchEvent(pointer('pointerup', 1000))
    })
    expect(result.current.width).toBe(420)
    node.remove()
  })

  it('向上拖超过上限也被钳制', () => {
    const { result } = renderHook(() => usePanelResize(true))
    const node = document.createElement('aside')
    document.body.appendChild(node)
    act(() => {
      result.current.setPanelRef(node)
    })

    act(() => {
      result.current.onHandlePointerDown(pointer('pointerdown', 1000) as never)
    })
    act(() => {
      window.dispatchEvent(pointer('pointermove', -5000))
    })
    act(() => {
      window.dispatchEvent(pointer('pointerup', -5000))
    })
    expect(result.current.width).toBe(1120)
    node.remove()
  })

  it('未移动直接松手：不写 localStorage', () => {
    const { result } = renderHook(() => usePanelResize(true))
    const node = document.createElement('aside')
    document.body.appendChild(node)
    act(() => {
      result.current.setPanelRef(node)
    })

    act(() => {
      result.current.onHandlePointerDown(pointer('pointerdown', 1000) as never)
    })
    act(() => {
      window.dispatchEvent(pointer('pointerup', 1000))
    })
    expect(result.current.width).toBe(600)
    expect(localStorage.getItem(WIDTH_KEY)).toBeNull()
    node.remove()
  })
})
