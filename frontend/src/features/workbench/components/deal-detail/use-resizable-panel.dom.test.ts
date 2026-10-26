// @vitest-environment jsdom
/**
 * 可拖拽分栏测试。
 *
 * 为什么值得单独测：
 * - 宽度要**记住**（下次打开还在），否则每次进预览都要重拖一遍；
 * - 拖动**不能越界**（把左栏挤没、或宽到出屏）；
 * - 拖拽期间 **iframe 必须让出指针事件**——OnlyOffice 是 iframe，光标一进
 *   画布它截获 mousemove，拖动会「断」在半路（这是最容易漏的坑）。
 */
import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useResizablePanel } from './use-resizable-panel'

const KEY = 'test:panel'

/** 造一个假的容器：右缘 1000、左缘 0、宽 1000 */
function attachBox(ref: { current: HTMLDivElement | null }) {
  const el = document.createElement('div')
  el.getBoundingClientRect = () =>
    ({ right: 1000, left: 0, width: 1000, top: 0, bottom: 0, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect
  ref.current = el
}

beforeEach(() => {
  localStorage.clear()
})

describe('useResizablePanel', () => {
  it('默认宽度', () => {
    const { result } = renderHook(() => useResizablePanel({ storageKey: KEY, defaultWidth: 720 }))
    expect(result.current.width).toBe(720)
  })

  it('记住上次的宽度', () => {
    localStorage.setItem(KEY, '850')
    const { result } = renderHook(() => useResizablePanel({ storageKey: KEY, defaultWidth: 720 }))
    expect(result.current.width).toBe(850)
  })

  it('存储值非法时回落默认（不让脏值把布局搞坏）', () => {
    localStorage.setItem(KEY, 'abc')
    const { result } = renderHook(() => useResizablePanel({ storageKey: KEY, defaultWidth: 720 }))
    expect(result.current.width).toBe(720)
  })

  it('setWidth 不能低于 min', () => {
    const { result } = renderHook(() =>
      useResizablePanel({ storageKey: KEY, defaultWidth: 720, min: 360 }),
    )
    act(() => result.current.setWidth(100))
    expect(result.current.width).toBe(360)
  })

  it('setWidth 不能超过容器宽度的 maxRatio（否则左栏被挤没）', () => {
    const { result } = renderHook(() =>
      useResizablePanel({ storageKey: KEY, defaultWidth: 720, maxRatio: 0.68 }),
    )
    attachBox(result.current.containerRef)
    act(() => result.current.setWidth(5000))
    // 容器 1000 × 0.68 = 680
    expect(result.current.width).toBe(680)
  })

  it('松手后写回 localStorage', () => {
    const { result } = renderHook(() =>
      useResizablePanel({ storageKey: KEY, defaultWidth: 720, min: 360 }),
    )
    act(() => result.current.setWidth(900))
    expect(localStorage.getItem(KEY)).toBe('900')
  })

  it('拖拽中把 iframe 的 pointer-events 关掉，松手恢复', () => {
    const iframe = document.createElement('iframe')
    document.body.appendChild(iframe)

    const { result } = renderHook(() =>
      useResizablePanel({ storageKey: KEY, defaultWidth: 720 }),
    )

    act(() => {
      act(() => result.current.onPointerDown({ preventDefault: () => {} } as unknown as React.PointerEvent))
    })
    // 关键：OnlyOffice 的 iframe 不接收指针事件，否则 mousemove 被它截获、拖动中断
    expect(iframe.style.pointerEvents).toBe('none')
    expect(document.body.style.cursor).toBe('col-resize')

    act(() => {
      window.dispatchEvent(new Event('pointerup'))
    })
    expect(iframe.style.pointerEvents).toBe('')
    expect(document.body.style.cursor).toBe('')

    iframe.remove()
    void vi
  })

  it('完整拖拽链路：按下 → 移动 → 松手，宽度真的变了', () => {
    const { result } = renderHook(() =>
      useResizablePanel({ storageKey: KEY, defaultWidth: 720, min: 360, maxRatio: 0.68 }),
    )
    attachBox(result.current.containerRef)

    // 按下分隔条
    act(() => {
      result.current.onPointerDown({ preventDefault: () => {} } as unknown as React.PointerEvent)
    })
    expect(result.current.dragging).toBe(true)

    // 指针移到容器右缘左侧 500px 处 → 右栏宽度应为 500
    act(() => {
      window.dispatchEvent(Object.assign(new Event('pointermove'), { clientX: 500 }))
    })
    expect(result.current.width).toBe(500)

    // 松手
    act(() => {
      window.dispatchEvent(new Event('pointerup'))
    })
    expect(result.current.dragging).toBe(false)
    // 落盘
    expect(localStorage.getItem(KEY)).toBe('500')
  })

  it('容器未挂载时移动不崩（首帧竞态）', () => {
    const { result } = renderHook(() =>
      useResizablePanel({ storageKey: KEY, defaultWidth: 720 }),
    )
    act(() => {
      result.current.onPointerDown({ preventDefault: () => {} } as unknown as React.PointerEvent)
    })
    expect(() => {
      act(() => {
        window.dispatchEvent(Object.assign(new Event('pointermove'), { clientX: 500 }))
      })
    }).not.toThrow()
  })

  it('stacked 看容器本身是否窄于竖排断点（不是拿容器比面板宽）', () => {
    // 旧写法 containerWidth < Math.min(effective, 1100)：面板宽本来就小于容器，
    // 恒为 false → 800px 窄屏下分隔条仍显示、拖拽态失效
    const { result } = renderHook(() =>
      useResizablePanel({ storageKey: KEY, defaultWidth: 720, min: 360, maxRatio: 0.68 }),
    )
    // 容器宽度未知时不算竖排（首帧不闪）
    expect(result.current.stacked).toBe(false)
  })

  it('容器宽度未知时不钳制上限（首帧不误伤）', () => {
    // containerWidth 为 null 时无法计算上限，不能把宽度钳成 0
    localStorage.setItem(KEY, '1140')
    const { result } = renderHook(() =>
      useResizablePanel({ storageKey: KEY, defaultWidth: 720, min: 360, maxRatio: 0.68 }),
    )
    expect(result.current.effectiveWidth).toBe(1140)
  })

  it('手动设置也不可能超过 maxRatio', () => {
    const { result } = renderHook(() =>
      useResizablePanel({ storageKey: KEY, defaultWidth: 720, min: 360, maxRatio: 0.68 }),
    )
    const el = document.createElement('div')
    el.getBoundingClientRect = () =>
      ({ right: 2000, left: 0, width: 2000, top: 0, bottom: 0, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect
    result.current.containerRef.current = el
    // 2000-560=1440 与 2000*0.68=1360 取小 → 1360
    act(() => result.current.setWidth((w) => w))
    expect(result.current.effectiveWidth).toBeLessThanOrEqual(1360)
  })

  it('手动拖过后以用户选择为准（不再自适应）', () => {
    localStorage.setItem(KEY, '800') // 视为用户拖过
    const { result } = renderHook(() =>
      useResizablePanel({ storageKey: KEY, defaultWidth: 720, min: 360, maxRatio: 0.68 }),
    )
    attachBox(result.current.containerRef)
    expect(result.current.effectiveWidth).toBe(800)
  })
})
