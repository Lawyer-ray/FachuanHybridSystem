// @vitest-environment jsdom
/**
 * useSplitDrag / useDialogWidthDrag 测试（jsdom）。
 *
 * 纯函数部分（initialSplitPct / initialDialogWidth）覆盖记忆值的合法性判定；
 * 拖拽部分覆盖拖拽期间的辅助样式复位与百分比映射。
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  DEFAULT_SPLIT_PCT,
  DIALOG_WIDTH_KEY,
  MAX_SPLIT_PCT,
  MIN_DIALOG_WIDTH,
  MIN_SPLIT_PCT,
  SPLIT_PCT_KEY,
} from '../constants'
import { initialDialogWidth, initialSplitPct, useDialogWidthDrag, useSplitDrag } from './use-split-drag'

function storage(initial: Record<string, string> = {}) {
  const map = new Map(Object.entries(initial))
  return {
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => {
      map.set(k, v)
    },
  }
}

describe('initialSplitPct', () => {
  it('无记忆时用默认值', () => {
    expect(initialSplitPct(storage())).toBe(DEFAULT_SPLIT_PCT)
  })

  it('合法记忆值沿用', () => {
    const mid = Math.round((MIN_SPLIT_PCT + MAX_SPLIT_PCT) / 2)
    expect(initialSplitPct(storage({ [SPLIT_PCT_KEY]: String(mid) }))).toBe(mid)
  })

  it('低于下限回落默认', () => {
    expect(initialSplitPct(storage({ [SPLIT_PCT_KEY]: String(MIN_SPLIT_PCT - 1) }))).toBe(DEFAULT_SPLIT_PCT)
  })

  it('高于上限回落默认', () => {
    expect(initialSplitPct(storage({ [SPLIT_PCT_KEY]: String(MAX_SPLIT_PCT + 1) }))).toBe(DEFAULT_SPLIT_PCT)
  })

  it('非数字回落默认', () => {
    expect(initialSplitPct(storage({ [SPLIT_PCT_KEY]: 'abc' }))).toBe(DEFAULT_SPLIT_PCT)
  })

  it('边界值本身合法', () => {
    expect(initialSplitPct(storage({ [SPLIT_PCT_KEY]: String(MIN_SPLIT_PCT) }))).toBe(MIN_SPLIT_PCT)
    expect(initialSplitPct(storage({ [SPLIT_PCT_KEY]: String(MAX_SPLIT_PCT) }))).toBe(MAX_SPLIT_PCT)
  })
})

describe('initialDialogWidth', () => {
  it('无记忆返回 null（走 CSS 默认）', () => {
    expect(initialDialogWidth(storage())).toBeNull()
  })

  it('低于下限返回 null', () => {
    expect(initialDialogWidth(storage({ [DIALOG_WIDTH_KEY]: String(MIN_DIALOG_WIDTH - 1) }))).toBeNull()
  })

  it('达到下限返回该值', () => {
    expect(initialDialogWidth(storage({ [DIALOG_WIDTH_KEY]: String(MIN_DIALOG_WIDTH + 100) }))).toBe(
      MIN_DIALOG_WIDTH + 100,
    )
  })

  it('非数字返回 null', () => {
    expect(initialDialogWidth(storage({ [DIALOG_WIDTH_KEY]: 'x' }))).toBeNull()
  })
})

describe('useSplitDrag', () => {
  beforeEach(() => {
    localStorage.clear()
    Object.defineProperty(HTMLElement.prototype, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({ left: 0, width: 1000, top: 0, height: 800, right: 1000, bottom: 800, x: 0, y: 0, toJSON: () => ({}) }),
    })
  })

  afterEach(() => {
    document.body.style.userSelect = ''
    document.body.style.cursor = ''
  })

  it('初始不处于拖拽态', () => {
    const { result } = renderHook(() => useSplitDrag())
    expect(result.current[3]).toBe(false)
  })

  it('开始拖拽设置 col-resize 光标与禁选中，结束后复位', () => {
    const { result } = renderHook(() => useSplitDrag())

    // 容器 ref 需要真实节点，这里手动挂一个
    const div = document.createElement('div')
    document.body.appendChild(div)
    ;(result.current[2] as { current: HTMLDivElement | null }).current = div

    act(() => {
      result.current[1]()
    })
    expect(result.current[3]).toBe(true)
    expect(document.body.style.cursor).toBe('col-resize')
    expect(document.body.style.userSelect).toBe('none')

    act(() => {
      window.dispatchEvent(new MouseEvent('mouseup'))
    })
    expect(result.current[3]).toBe(false)
    expect(document.body.style.cursor).toBe('')
    expect(document.body.style.userSelect).toBe('')

    div.remove()
  })

  it('拖拽结束把光标还原成原值而不是清空（不抹掉页面上已设的内联样式）', () => {
    // 旧实现硬复位 cursor: ''，拖拽前元素上已有的光标样式会被抹掉
    document.body.style.cursor = 'progress'
    const { result } = renderHook(() => useSplitDrag())
    const div = document.createElement('div')
    document.body.appendChild(div)
    ;(result.current[2] as { current: HTMLDivElement | null }).current = div

    act(() => {
      result.current[1]()
    })
    expect(document.body.style.cursor).toBe('col-resize')

    act(() => {
      window.dispatchEvent(new MouseEvent('mouseup'))
    })
    expect(document.body.style.cursor).toBe('progress')
    document.body.style.cursor = ''
    div.remove()
  })

  it('pointercancel 也结束拖拽并复位样式（触摸被系统手势打断）', () => {
    const { result } = renderHook(() => useSplitDrag())
    const div = document.createElement('div')
    document.body.appendChild(div)
    ;(result.current[2] as { current: HTMLDivElement | null }).current = div

    act(() => {
      result.current[1]()
    })
    expect(result.current[3]).toBe(true)

    act(() => {
      window.dispatchEvent(new Event('pointercancel'))
    })
    expect(result.current[3]).toBe(false)
    expect(document.body.style.cursor).toBe('')
    expect(document.body.style.userSelect).toBe('')
    div.remove()
  })

  it('拖拽中移动鼠标按容器宽度换算百分比并夹在范围内', () => {
    const { result } = renderHook(() => useSplitDrag())
    const div = document.createElement('div')
    document.body.appendChild(div)
    ;(result.current[2] as { current: HTMLDivElement | null }).current = div

    act(() => {
      result.current[1]()
    })
    // 容器宽 1000，鼠标 x=900 → 90%，应被夹到 MAX_SPLIT_PCT
    act(() => {
      window.dispatchEvent(new MouseEvent('mousemove', { clientX: 900 }))
    })
    expect(result.current[0]).toBeLessThanOrEqual(MAX_SPLIT_PCT)
    expect(result.current[0]).toBeGreaterThanOrEqual(MIN_SPLIT_PCT)

    // 鼠标 x=10 → 1%，夹到下限
    act(() => {
      window.dispatchEvent(new MouseEvent('mousemove', { clientX: 10 }))
    })
    expect(result.current[0]).toBeGreaterThanOrEqual(MIN_SPLIT_PCT)

    act(() => {
      window.dispatchEvent(new MouseEvent('mouseup'))
    })
    div.remove()
  })

  it('卸载时清理监听（不再响应 move）', () => {
    const { result, unmount } = renderHook(() => useSplitDrag())
    const div = document.createElement('div')
    document.body.appendChild(div)
    ;(result.current[2] as { current: HTMLDivElement | null }).current = div

    act(() => {
      result.current[1]()
    })
    unmount()

    // 卸载后派发事件不应抛错
    expect(() => {
      window.dispatchEvent(new MouseEvent('mousemove', { clientX: 500 }))
    }).not.toThrow()
    div.remove()
  })
})

// ============ useDialogWidthDrag（覆盖率补测） ============

describe('useDialogWidthDrag', () => {
  beforeEach(() => {
    localStorage.clear()
    Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: 1440 })
  })

  it('无记忆值时初始宽度为 null（走 CSS 自适应）', () => {
    const { result } = renderHook(() => useDialogWidthDrag())
    expect(result.current[0]).toBeNull()
    expect(result.current[2]).toBe(false)
  })

  it('有合法记忆值时沿用', () => {
    localStorage.setItem(DIALOG_WIDTH_KEY, String(MIN_DIALOG_WIDTH + 100))
    const { result } = renderHook(() => useDialogWidthDrag())
    expect(result.current[0]).toBe(MIN_DIALOG_WIDTH + 100)
  })

  it('开始拖拽进入 dragging 态并 preventDefault', () => {
    const { result } = renderHook(() => useDialogWidthDrag())
    const preventDefault = vi.fn()
    const dialog = document.createElement('div')
    dialog.setAttribute('role', 'dialog')
    document.body.appendChild(dialog)

    act(() => {
      result.current[1]({ preventDefault, clientX: 500, currentTarget: dialog })
    })

    expect(preventDefault).toHaveBeenCalled()
    expect(result.current[2]).toBe(true)
    dialog.remove()
  })

  it('拖拽移动按位移更新宽度并钳在最小值之上', () => {
    const { result } = renderHook(() => useDialogWidthDrag())
    const dialog = document.createElement('div')
    dialog.setAttribute('role', 'dialog')
    Object.defineProperty(dialog, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({ width: 800, top: 0, left: 0, right: 0, bottom: 0, height: 0, x: 0, y: 0, toJSON: () => ({}) }),
    })
    document.body.appendChild(dialog)

    act(() => {
      result.current[1]({ preventDefault: vi.fn(), clientX: 500, currentTarget: dialog })
    })

    act(() => {
      window.dispatchEvent(new MouseEvent('mousemove', { clientX: 700 }))
    })
    // 800 + (700-500) = 1000
    expect(result.current[0]).toBe(1000)

    // 往左拖到极小 → 钳到 MIN_DIALOG_WIDTH
    act(() => {
      window.dispatchEvent(new MouseEvent('mousemove', { clientX: -5000 }))
    })
    expect(result.current[0]).toBe(MIN_DIALOG_WIDTH)

    act(() => {
      window.dispatchEvent(new MouseEvent('mouseup'))
    })
    expect(result.current[2]).toBe(false)
    dialog.remove()
  })

  it('松手后把宽度写入 localStorage', () => {
    const { result } = renderHook(() => useDialogWidthDrag())
    const dialog = document.createElement('div')
    dialog.setAttribute('role', 'dialog')
    Object.defineProperty(dialog, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({ width: 900, top: 0, left: 0, right: 0, bottom: 0, height: 0, x: 0, y: 0, toJSON: () => ({}) }),
    })
    document.body.appendChild(dialog)

    act(() => {
      result.current[1]({ preventDefault: vi.fn(), clientX: 100, currentTarget: dialog })
    })
    act(() => {
      window.dispatchEvent(new MouseEvent('mousemove', { clientX: 200 }))
    })
    act(() => {
      window.dispatchEvent(new MouseEvent('mouseup'))
    })

    expect(localStorage.getItem(DIALOG_WIDTH_KEY)).toBe('1000')
    dialog.remove()
  })

  it('窗口缩放后有效宽度被钳到视口内（存储值不变）', () => {
    localStorage.setItem(DIALOG_WIDTH_KEY, '1200')
    const { result } = renderHook(() => useDialogWidthDrag())
    expect(result.current[0]).toBe(1200)

    // 视口缩到 800 → 1200 被钳到 768
    act(() => {
      Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: 800 })
      window.dispatchEvent(new Event('resize'))
    })
    expect(result.current[0]).toBe(768)
    // 存储值不被改写
    expect(localStorage.getItem(DIALOG_WIDTH_KEY)).toBe('1200')
  })

  it('无 role=dialog 祖先时用 MIN_DIALOG_WIDTH 作为起始宽', () => {
    const { result } = renderHook(() => useDialogWidthDrag())
    const el = document.createElement('div')
    document.body.appendChild(el)

    act(() => {
      result.current[1]({ preventDefault: vi.fn(), clientX: 100, currentTarget: el })
    })
    act(() => {
      window.dispatchEvent(new MouseEvent('mousemove', { clientX: 200 }))
    })
    expect(result.current[0]).toBe(MIN_DIALOG_WIDTH + 100)

    act(() => {
      window.dispatchEvent(new MouseEvent('mouseup'))
    })
    el.remove()
  })

  it('卸载后移除 resize 监听', () => {
    const { unmount } = renderHook(() => useDialogWidthDrag())
    unmount()
    expect(() => window.dispatchEvent(new Event('resize'))).not.toThrow()
  })
})
