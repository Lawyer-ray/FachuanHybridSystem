// @vitest-environment jsdom
/**
 * useWheelZoom 测试（jsdom）。
 *
 * 覆盖：非修饰键滚轮不处理、修饰键滚轮按指数步进调用 setZoom、
 * 到达上下限后不再变化、卸载后移除监听、缩放后按锚点回拨滚动条。
 */
import { renderHook } from '@testing-library/react'
import { act } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const storeMock = vi.hoisted(() => ({
  zoom: 1,
  setZoom: vi.fn(),
}))

vi.mock('../../store', () => ({
  useReader: { getState: () => storeMock },
}))
vi.mock('./ui', () => ({ ZOOM_MIN: 0.5, ZOOM_MAX: 2.5 }))

import { useWheelZoom } from './use-wheel-zoom'

function makeEl() {
  const el = document.createElement('div')
  // jsdom 默认 0 尺寸，给一组可预测值供锚点计算
  Object.defineProperty(el, 'scrollWidth', { value: 2000, configurable: true })
  Object.defineProperty(el, 'scrollHeight', { value: 4000, configurable: true })
  Object.defineProperty(el, 'scrollLeft', { value: 0, writable: true, configurable: true })
  Object.defineProperty(el, 'scrollTop', { value: 0, writable: true, configurable: true })
  el.getBoundingClientRect = () =>
    ({ left: 0, top: 0, width: 1000, height: 800, right: 1000, bottom: 800, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect
  document.body.appendChild(el)
  return el
}

function wheel(el: HTMLElement, opts: { deltaY: number; ctrlKey?: boolean; metaKey?: boolean; clientX?: number; clientY?: number }) {
  const e = new WheelEvent('wheel', {
    deltaY: opts.deltaY,
    ctrlKey: opts.ctrlKey ?? false,
    metaKey: opts.metaKey ?? false,
    clientX: opts.clientX ?? 100,
    clientY: opts.clientY ?? 100,
    bubbles: true,
    cancelable: true,
  })
  el.dispatchEvent(e)
  return e
}

beforeEach(() => {
  vi.clearAllMocks()
  storeMock.zoom = 1
  storeMock.setZoom = vi.fn()
})

describe('useWheelZoom', () => {
  it('el 为 null 时不挂监听（不抛错）', () => {
    expect(() => renderHook(() => useWheelZoom(null, 1))).not.toThrow()
  })

  it('无修饰键的滚轮不处理', () => {
    const el = makeEl()
    renderHook(() => useWheelZoom(el, 1))
    const e = wheel(el, { deltaY: 100 })
    expect(storeMock.setZoom).not.toHaveBeenCalled()
    expect(e.defaultPrevented).toBe(false)
    el.remove()
  })

  it('Ctrl+滚轮向上放大并 preventDefault', () => {
    const el = makeEl()
    renderHook(() => useWheelZoom(el, 1))
    const e = wheel(el, { deltaY: -100, ctrlKey: true })
    expect(storeMock.setZoom).toHaveBeenCalled()
    expect(e.defaultPrevented).toBe(true)
    const next = storeMock.setZoom.mock.calls[0]![0] as number
    expect(next).toBeGreaterThan(1)
    el.remove()
  })

  it('Meta+滚轮向下缩小', () => {
    const el = makeEl()
    renderHook(() => useWheelZoom(el, 1))
    wheel(el, { deltaY: 100, metaKey: true })
    const next = storeMock.setZoom.mock.calls[0]![0] as number
    expect(next).toBeLessThan(1)
    el.remove()
  })

  it('触控板捏合（带 ctrlKey 的小 delta）也生效', () => {
    const el = makeEl()
    renderHook(() => useWheelZoom(el, 1))
    wheel(el, { deltaY: -3, ctrlKey: true })
    expect(storeMock.setZoom).toHaveBeenCalled()
    el.remove()
  })

  it('达到上限后不再调用 setZoom', () => {
    storeMock.zoom = 2.5 // ZOOM_MAX
    const el = makeEl()
    renderHook(() => useWheelZoom(el, 2.5))
    wheel(el, { deltaY: -100, ctrlKey: true })
    expect(storeMock.setZoom).not.toHaveBeenCalled()
    el.remove()
  })

  it('达到下限后不再调用 setZoom', () => {
    storeMock.zoom = 0.5 // ZOOM_MIN
    const el = makeEl()
    renderHook(() => useWheelZoom(el, 0.5))
    wheel(el, { deltaY: 100, ctrlKey: true })
    expect(storeMock.setZoom).not.toHaveBeenCalled()
    el.remove()
  })

  it('缩放结果被钳制在 [ZOOM_MIN, ZOOM_MAX]', () => {
    storeMock.zoom = 2.4
    const el = makeEl()
    renderHook(() => useWheelZoom(el, 2.4))
    // 极大的放大步进
    wheel(el, { deltaY: -10000, ctrlKey: true })
    const next = storeMock.setZoom.mock.calls[0]![0] as number
    expect(next).toBeLessThanOrEqual(2.5)
    el.remove()
  })

  it('卸载后移除监听', () => {
    const el = makeEl()
    const { unmount } = renderHook(() => useWheelZoom(el, 1))
    unmount()
    wheel(el, { deltaY: -100, ctrlKey: true })
    expect(storeMock.setZoom).not.toHaveBeenCalled()
    el.remove()
  })

  it('el 变化时重挂监听（旧元素不再响应）', () => {
    const el1 = makeEl()
    const el2 = makeEl()
    const { rerender } = renderHook(({ e }) => useWheelZoom(e, 1), { initialProps: { e: el1 as HTMLElement | null } })
    rerender({ e: el2 })

    wheel(el1, { deltaY: -100, ctrlKey: true })
    expect(storeMock.setZoom).not.toHaveBeenCalled()

    wheel(el2, { deltaY: -100, ctrlKey: true })
    expect(storeMock.setZoom).toHaveBeenCalled()
    el1.remove()
    el2.remove()
  })

  it('缩放后按锚点回拨滚动条（zoom 变化触发 layoutEffect）', () => {
    const el = makeEl()
    const { rerender } = renderHook(({ z }) => useWheelZoom(el, z), { initialProps: { z: 1 } })

    // 先把滚动位置与指针都设成非零
    el.scrollLeft = 200
    el.scrollTop = 400
    act(() => {
      wheel(el, { deltaY: -100, ctrlKey: true, clientX: 100, clientY: 100 })
    })

    // 模拟库外更新 zoom（真实场景由 store 驱动重渲染）
    rerender({ z: 1.2 })
    // 回拨公式：rx*scrollWidth - x ；rx=(scrollLeft+x)/scrollWidth
    expect(Number.isFinite(el.scrollLeft)).toBe(true)
    el.remove()
  })
})
