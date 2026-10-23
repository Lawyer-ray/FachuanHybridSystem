// @vitest-environment jsdom
/**
 * useReaderKeys 键位测试（jsdom）。
 *
 * Esc 的逐级退出顺序是本模块最容易退化的一段：
 * 归案弹窗 → OCR 待确认 → 选页模式 → 有选页 → 取字态 → 关闭阅读器。
 * 顺序错了就会「弹窗开着按 Esc 把整个阅读器关掉」。
 */
import { renderHook } from '@testing-library/react'
import { act } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const state = vi.hoisted(() => ({
  assignOpen: false,
  ocrPending: null as unknown,
  selMode: false,
  selPages: [] as number[],
  pickInfo: -1,
  calls: [] as string[],
}))

vi.mock('../../store', () => ({
  useReader: {
    getState: () => ({
      assignOpen: state.assignOpen,
      ocrPending: state.ocrPending,
      selMode: state.selMode,
      selPages: state.selPages,
      pickInfo: state.pickInfo,
      setAssignOpen: () => state.calls.push('setAssignOpen'),
      setOcrPending: () => state.calls.push('setOcrPending'),
      setPickInfo: () => state.calls.push('setPickInfo'),
      clearSel: () => state.calls.push('clearSel'),
      toggleSelMode: () => state.calls.push('toggleSelMode'),
      close: () => state.calls.push('close'),
      applySel: () => state.calls.push('applySel'),
    }),
  },
}))

import { useReaderKeys } from './use-reader-keys'

function press(key: string, target?: HTMLElement) {
  const e = new KeyboardEvent('keydown', { key, cancelable: true, bubbles: true })
  if (target) Object.defineProperty(e, 'target', { value: target })
  window.dispatchEvent(e)
  return e
}

beforeEach(() => {
  state.assignOpen = false
  state.ocrPending = null
  state.selMode = false
  state.selPages = []
  state.pickInfo = -1
  state.calls = []
})

describe('useReaderKeys / Esc 逐级退出', () => {
  it('归案弹窗开启时：只关弹窗，不关阅读器', () => {
    state.assignOpen = true
    renderHook(() => useReaderKeys())
    act(() => {
      press('Escape')
    })
    expect(state.calls).toEqual(['setAssignOpen'])
  })

  it('OCR 待确认：清待确认并复位取字态', () => {
    state.ocrPending = { x: 1 }
    renderHook(() => useReaderKeys())
    act(() => {
      press('Escape')
    })
    expect(state.calls).toEqual(['setOcrPending', 'setPickInfo'])
  })

  it('选页模式：清选中并退出模式', () => {
    state.selMode = true
    renderHook(() => useReaderKeys())
    act(() => {
      press('Escape')
    })
    expect(state.calls).toEqual(['clearSel', 'toggleSelMode'])
  })

  it('有选中页：只清选中', () => {
    state.selPages = [1, 2]
    renderHook(() => useReaderKeys())
    act(() => {
      press('Escape')
    })
    expect(state.calls).toEqual(['clearSel'])
  })

  it('取字态：复位 pickInfo', () => {
    state.pickInfo = 2
    renderHook(() => useReaderKeys())
    act(() => {
      press('Escape')
    })
    expect(state.calls).toEqual(['setPickInfo'])
  })

  it('无任何中间态：关闭阅读器', () => {
    renderHook(() => useReaderKeys())
    act(() => {
      press('Escape')
    })
    expect(state.calls).toEqual(['close'])
  })

  it('Esc 会 preventDefault（避免浏览器默认行为）', () => {
    renderHook(() => useReaderKeys())
    let prevented = false
    act(() => {
      prevented = press('Escape').defaultPrevented
    })
    expect(prevented).toBe(true)
  })
})

describe('useReaderKeys / S 合并选中页', () => {
  it('有选中页时按 s 触发合并', () => {
    state.selPages = [3]
    renderHook(() => useReaderKeys())
    act(() => {
      press('s')
    })
    expect(state.calls).toContain('applySel')
  })

  it('无选中页时按 s 不触发', () => {
    renderHook(() => useReaderKeys())
    act(() => {
      press('s')
    })
    expect(state.calls).not.toContain('applySel')
  })

  it('带修饰键（Ctrl/Meta/Shift/Alt）时不触发合并', () => {
    state.selPages = [3]
    renderHook(() => useReaderKeys())
    for (const mod of ['ctrlKey', 'metaKey', 'shiftKey', 'altKey']) {
      state.calls = []
      const e = new KeyboardEvent('keydown', { key: 's', cancelable: true, [mod]: true })
      window.dispatchEvent(e)
      expect(state.calls).not.toContain('applySel')
    }
  })
})

describe('useReaderKeys / 输入框豁免', () => {
  it('焦点在 input 内时不劫持 Esc', () => {
    const input = document.createElement('input')
    document.body.appendChild(input)
    renderHook(() => useReaderKeys())
    act(() => {
      press('Escape', input)
    })
    expect(state.calls).toEqual([])
    input.remove()
  })

  it('焦点在 textarea / select 内同样豁免', () => {
    const ta = document.createElement('textarea')
    document.body.appendChild(ta)
    renderHook(() => useReaderKeys())
    act(() => {
      press('Escape', ta)
    })
    expect(state.calls).toEqual([])
    ta.remove()
  })

  it('卸载后移除监听器', () => {
    const { unmount } = renderHook(() => useReaderKeys())
    unmount()
    act(() => {
      press('Escape')
    })
    expect(state.calls).toEqual([])
  })
})
