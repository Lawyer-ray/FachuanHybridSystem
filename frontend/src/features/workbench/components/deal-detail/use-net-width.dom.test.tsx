// @vitest-environment jsdom
/**
 * useNetWidth：页面净宽 = `100vw − AI 助手宽度`。
 *
 * **为什么必须自算**：助手是 `position: fixed` 抽屉，不占文档流，容器查询与
 * ResizeObserver 都测不到它；宽屏下助手恒并排让位，主区被压掉数百像素。
 * 这里锁死的是「读哪个 CSS 变量、在什么事件上重算」这两件事。
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/hooks/use-media', () => ({ useMediaQuery: (q: string) => q.includes('1280') }))

import { useDockedViewport, useNetWidth } from './use-net-width'

const realGetComputedStyle = globalThis.getComputedStyle

function stubHelperWidth(cssValue: string) {
  vi.stubGlobal(
    'getComputedStyle',
    vi.fn(() => ({ getPropertyValue: (p: string) => (p === '--copilot-w-app' ? cssValue : '') })),
  )
}

function setViewportWidth(width: number) {
  Object.defineProperty(window, 'innerWidth', { value: width, configurable: true, writable: true })
}

beforeEach(() => {
  setViewportWidth(1600)
  stubHelperWidth('')
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  globalThis.getComputedStyle = realGetComputedStyle
})

describe('useNetWidth', () => {
  it('助手未并排（变量为空）时净宽 = 视口宽', () => {
    const { result } = renderHook(() => useNetWidth())
    expect(result.current).toBe(1600)
  })

  it('助手并排时扣掉像素宽度（--copilot-w-app 带 px）', () => {
    stubHelperWidth('600px')
    const { result } = renderHook(() => useNetWidth())
    expect(result.current).toBe(1000)
  })

  it('变量不带 px 时按 0 处理（容错不合规的写法）', () => {
    stubHelperWidth('600')
    const { result } = renderHook(() => useNetWidth())
    expect(result.current).toBe(1600)
  })

  it('非数值的 px 值按 0 处理', () => {
    stubHelperWidth('abcpx')
    const { result } = renderHook(() => useNetWidth())
    expect(result.current).toBe(1600)
  })

  it('窗口 resize 时重算', () => {
    const { result } = renderHook(() => useNetWidth())
    expect(result.current).toBe(1600)
    setViewportWidth(1200)
    act(() => {
      window.dispatchEvent(new Event('resize'))
    })
    expect(result.current).toBe(1200)
  })

  it('助手拖动广播 copilot-width-change 时重算', () => {
    const { result } = renderHook(() => useNetWidth())
    expect(result.current).toBe(1600)
    stubHelperWidth('600px')
    act(() => {
      document.documentElement.dispatchEvent(new Event('copilot-width-change'))
    })
    expect(result.current).toBe(1000)
  })

  it('卸载后摘掉两个监听（否则拖助手会持续触发已卸载组件的 setState）', () => {
    const removeSpy = vi.spyOn(window, 'removeEventListener')
    const docRemoveSpy = vi.spyOn(document.documentElement, 'removeEventListener')
    const { unmount } = renderHook(() => useNetWidth())
    unmount()
    expect(removeSpy).toHaveBeenCalledWith('resize', expect.any(Function))
    expect(docRemoveSpy).toHaveBeenCalledWith('copilot-width-change', expect.any(Function))
  })
})

describe('useDockedViewport', () => {
  it('宽屏判定走 (min-width: 1280px) 媒体查询', () => {
    const { result } = renderHook(() => useDockedViewport())
    expect(result.current).toBe(true)
  })
})
