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
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useResizablePanel } from './use-resizable-panel'

const KEY = 'test:panel'

/**
 * ResizeObserver 桩：记录最后一次回调，让用例能手动「报告」容器宽度。
 *
 * 为什么要桩：量宽改由 useElementWidth（clientWidth + ResizeObserver）负责，
 * 而 jsdom 的 clientWidth 恒 0，不桩的话容器宽永远是「未知」，钳制相关用例
 * 测不到真东西。
 */
let roCb: ResizeObserverCallback | null = null
function installResizeObserver() {
  roCb = null
  vi.stubGlobal(
    'ResizeObserver',
    class {
      constructor(cb: ResizeObserverCallback) {
        roCb = cb
      }
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  )
}

/** 让 hook 认为容器实测宽度是 width（走 ResizeObserver 回调，与真实一致） */
function reportContainerWidth(width: number) {
  act(() => {
    roCb?.([{ contentRect: { width } } as ResizeObserverEntry], {} as ResizeObserver)
  })
}

/**
 * 造一个假的容器：右缘 1500、左缘 0、宽 1500。
 * 取 1500 是为了同时越过两个上限约束：竖排断点 1100（否则 width 为 undefined）、
 * 以及 maxRatio 与「容器 − 左栏下限 560」里更小的那个。
 *
 * 容器 ref 是 useElementWidth 的 callback ref（不是 ref 对象），直接把假节点
 * 喂给它即可。宽度要从 **clientWidth** 给——useElementWidth 量的是 clientWidth
 * （不含滚动条/边框的真净宽），只给 getBoundingClientRect 它测到的是 0。
 * getBoundingClientRect 仍是拖拽换算容器右缘用的，两者都给。
 *
 * await 一次：callback ref 只是 setState，元素进 state 后才建 ResizeObserver
 * 观察，紧跟着的 reportContainerWidth 才不会打空。
 */
async function attachBox(ref: (node: HTMLDivElement | null) => void, width = 1500) {
  const el = document.createElement('div')
  Object.defineProperty(el, 'clientWidth', { get: () => width, configurable: true })
  el.getBoundingClientRect = () =>
    ({ right: width, left: 0, width, top: 0, bottom: 0, x: 0, y: 0, toJSON: () => ({}) }) as DOMRect
  ref(el)
  await act(async () => {})
}

beforeEach(() => {
  localStorage.clear()
  installResizeObserver()
})

afterEach(() => {
  vi.unstubAllGlobals()
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

  it('setWidth 不能超过容器宽度的 maxRatio（否则左栏被挤没）', async () => {
    const { result } = renderHook(() =>
      useResizablePanel({ storageKey: KEY, defaultWidth: 720, maxRatio: 0.68 }),
    )
    await attachBox(result.current.containerRef)
    reportContainerWidth(1500)
    act(() => result.current.setWidth(5000))
    // 容器 1500 × 0.68 = 1020，容器 − 左栏下限 560 = 940，取小 → 940
    expect(result.current.width).toBe(940)
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

  it('完整拖拽链路：按下 → 移动 → 松手，宽度真的变了', async () => {
    const { result } = renderHook(() =>
      useResizablePanel({ storageKey: KEY, defaultWidth: 720, min: 360, maxRatio: 0.68 }),
    )
    await attachBox(result.current.containerRef)
    reportContainerWidth(1500)

    // 按下分隔条
    act(() => {
      result.current.onPointerDown({ preventDefault: () => {} } as unknown as React.PointerEvent)
    })
    expect(result.current.dragging).toBe(true)

    // 指针移到容器右缘左侧 500px 处（右缘 1500 → x=1000）→ 右栏宽度应为 500
    act(() => {
      window.dispatchEvent(Object.assign(new Event('pointermove'), { clientX: 1000 }))
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

  it('pointercancel 也结束拖拽并复位样式（触摸被系统手势打断）', async () => {
    // 触摸/笔拖拽被系统手势打断时浏览器只发 pointercancel，不补 pointerup。
    // 漏掉它则 dragging 卡死、userSelect: none 永久残留（整页选不中文字）。
    const { result } = renderHook(() =>
      useResizablePanel({ storageKey: KEY, defaultWidth: 720, min: 360, maxRatio: 0.68 }),
    )
    await attachBox(result.current.containerRef)
    reportContainerWidth(1500)

    act(() => {
      result.current.onPointerDown({ preventDefault: () => {} } as unknown as React.PointerEvent)
    })
    expect(result.current.dragging).toBe(true)
    expect(document.body.style.userSelect).toBe('none')

    act(() => {
      window.dispatchEvent(new Event('pointercancel'))
    })
    expect(result.current.dragging).toBe(false)
    expect(document.body.style.userSelect).toBe('')
    expect(document.body.style.cursor).toBe('')
  })

  it('拖拽期间改的是 body 内联样式，结束后还原原值而不是清空', () => {
    // 直接写 '' 会抹掉页面上本来就有的内联样式
    document.body.style.cursor = 'progress'
    const { result } = renderHook(() =>
      useResizablePanel({ storageKey: KEY, defaultWidth: 720, min: 360, maxRatio: 0.68 }),
    )
    act(() => {
      result.current.onPointerDown({ preventDefault: () => {} } as unknown as React.PointerEvent)
    })
    expect(document.body.style.cursor).toBe('col-resize')
    act(() => {
      window.dispatchEvent(new Event('pointerup'))
    })
    expect(document.body.style.cursor).toBe('progress')
    document.body.style.cursor = ''
  })

  it('卸载时收尾进行中的拖拽（样式不残留）', () => {
    const { result, unmount } = renderHook(() =>
      useResizablePanel({ storageKey: KEY, defaultWidth: 720, min: 360, maxRatio: 0.68 }),
    )
    act(() => {
      result.current.onPointerDown({ preventDefault: () => {} } as unknown as React.PointerEvent)
    })
    expect(document.body.style.userSelect).toBe('none')
    unmount()
    expect(document.body.style.userSelect).toBe('')
    expect(document.body.style.cursor).toBe('')
  })

  it('容器挂载即测到宽度（不依赖测试自己 stub ResizeObserver 之外的东西）', async () => {
    const { result } = renderHook(() =>
      useResizablePanel({ storageKey: KEY, defaultWidth: 720, min: 360, maxRatio: 0.68 }),
    )
    expect(result.current.containerWidth).toBeNull()
    await attachBox(result.current.containerRef, 900)
    expect(result.current.containerWidth).toBe(900)
    // 900 < 1100 竖排断点 → stacked
    expect(result.current.stacked).toBe(true)
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
    result.current.containerRef(el)
    // 2000-560=1440 与 2000*0.68=1360 取小 → 1360
    act(() => result.current.setWidth((w) => w))
    expect(result.current.effectiveWidth).toBeLessThanOrEqual(1360)
  })

  it('手动拖过后以用户选择为准（不再自适应）', async () => {
    localStorage.setItem(KEY, '800') // 视为用户拖过
    const { result } = renderHook(() =>
      useResizablePanel({ storageKey: KEY, defaultWidth: 720, min: 360, maxRatio: 0.68 }),
    )
    await attachBox(result.current.containerRef)
    expect(result.current.effectiveWidth).toBe(800)
  })
})
