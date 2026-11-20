// @vitest-environment jsdom
/**
 * `useScrollAnchor` 测试（jsdom，假 rect 布局）。
 *
 * jsdom 没有排版引擎：`getBoundingClientRect()` 恒返回全 0、`scrollTop` 也永远是 0。
 * 所以这里自己搭一个**最小布局模型**——视口高 300，行高可调，行的 rect 由
 * 「内容坐标 - scrollTop」实时算出。这样「上翻 60px」「切走再切回」「图片加载
 * 把上面的行撑高」都能量化断言，而不是靠 --approve 的目测。
 *
 * 被测的四条不变量（对应真实事故，不是覆盖率凑数）：
 * 1. 上翻 60px → 切到别的会话 → 切回来：位置**回到同一行同一偏移**（不是 scrollTop 相同）；
 * 2. 上面多出内容（翻页插入 / 图片撑高）时锚点跟随**行身份**走，scrollTop 根本不一样；
 * 3. 锚点行已不存在（消息被删/换批）→ 回落到保存的 scrollTop；
 * 4. 没有记录 / 没给会话 id / 没给容器 → **什么都不做**。
 */
import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { clearScrollAnchors, readScrollAnchor, useScrollAnchor } from './use-scroll-anchor'

const VIEWPORT = 300
const ROW_H = 100

/** 假 DOMRect（只填被测代码真正读的字段） */
function rect(top: number, height: number): DOMRect {
  return { top, y: top, bottom: top + height, height, left: 0, right: 0, width: 0, x: 0, toJSON: () => ({}) } as DOMRect
}

/** 造一个滚动容器：scrollTop 可读写，rect 固定为 [0, 300) */
function makeScroller(): HTMLElement {
  const el = document.createElement('div')
  document.body.appendChild(el)
  let top = 0
  Object.defineProperty(el, 'scrollTop', {
    configurable: true,
    get: () => top,
    set: (v: number) => {
      top = v
    },
  })
  Object.defineProperty(el, 'getBoundingClientRect', {
    configurable: true,
    value: () => rect(0, VIEWPORT),
  })
  return el
}

/**
 * 在容器里铺一批行（每条消息一个 `[data-msg-id]`）。
 * `heights` 传**数组引用**：改这个数组就等于「图片加载完、行变高了」——rect 每次
 * 读取时现算，不用重挂 DOM。
 */
function mountRows(el: HTMLElement, ids: string[], heights: number[]): HTMLElement {
  el.innerHTML = ''
  const wrap = document.createElement('div')
  el.appendChild(wrap)
  ids.forEach((id, i) => {
    const row = document.createElement('div')
    row.setAttribute('data-msg-id', id)
    Object.defineProperty(row, 'getBoundingClientRect', {
      configurable: true,
      value: () => {
        let contentTop = 0
        for (let k = 0; k < i; k++) contentTop += heights[k]!
        return rect(contentTop - el.scrollTop, heights[i]!)
      },
    })
    wrap.appendChild(row)
  })
  return wrap
}

const IDS_10 = ['db-1', 'db-2', 'db-3', 'db-4', 'db-5', 'db-6', 'db-7', 'db-8', 'db-9', 'db-10']

/** ResizeObserver 桩：记录实例，用例手动 fire（jsdom 里没有这个东西） */
class FakeRO {
  static instances: FakeRO[] = []
  readonly targets: Element[] = []
  disconnected = false
  constructor(private readonly cb: ResizeObserverCallback) {
    FakeRO.instances.push(this)
  }
  observe(t: Element): void {
    this.targets.push(t)
  }
  unobserve(): void {}
  disconnect(): void {
    this.disconnected = true
  }
  fire(): void {
    this.cb([], this as unknown as ResizeObserver)
  }
}

const hadRO = 'ResizeObserver' in globalThis

beforeEach(() => {
  clearScrollAnchors()
  FakeRO.instances = []
  ;(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = FakeRO
})

afterEach(() => {
  document.body.innerHTML = ''
  if (!hadRO) delete (globalThis as unknown as { ResizeObserver?: unknown }).ResizeObserver
})

/** 挂 hook，容器用手造的假元素 */
function setup(scroller: HTMLElement | null) {
  return renderHook(() => useScrollAnchor({ current: scroller }))
}

describe('useScrollAnchor：跨会话位置保持', () => {
  it('上翻 60px 后切走再切回：回到同一行同一偏移（位置不变）', () => {
    const scroller = makeScroller()
    const heights = Array.from({ length: 10 }, () => ROW_H)
    mountRows(scroller, IDS_10, heights)
    const { result } = setup(scroller)

    // 先到底（内容 1000 - 视口 300 = 700），再往上翻 60：这是律师阅读时的常态位置
    scroller.scrollTop = 700 - 60
    result.current.saveAnchor('A')
    // 锚点是「行身份 + 行顶偏移」，不是 scrollTop：db-7 的内容顶 600，视口顶 640 → -40
    expect(readScrollAnchor('A')).toEqual({ anchorKey: 'db-7', anchorTop: -40, scrollTop: 640 })

    // 切去 B 会话（另一个项目的 20 条消息），B 里也往上翻了一段
    const bHeights = Array.from({ length: 20 }, () => ROW_H)
    mountRows(scroller, Array.from({ length: 20 }, (_, i) => `b-${i + 1}`), bHeights)
    scroller.scrollTop = 1000
    result.current.saveAnchor('B')

    // 切回 A：DOM 是重建的（scrollTop 归 0），恢复只能靠锚点
    mountRows(scroller, IDS_10, heights)
    scroller.scrollTop = 0
    result.current.restoreAnchor('A')

    expect(scroller.scrollTop).toBe(640)
  })

  it('锚点行身份不随内容变化漂移：上面被撑高 300px 时回的不是 scrollTop 640', () => {
    const scroller = makeScroller()
    const heights = Array.from({ length: 10 }, () => ROW_H)
    mountRows(scroller, IDS_10, heights)
    const { result } = setup(scroller)

    scroller.scrollTop = 640
    result.current.saveAnchor('A')

    // 真实场景：翻页在顶上插入消息，或图片/字体把上面六行撑高。
    // 此时「同一段文字」还在 db-7，但它现在的内容顶变成了 900。
    for (let i = 0; i < 6; i++) heights[i] = 150
    mountRows(scroller, IDS_10, heights)
    scroller.scrollTop = 0
    result.current.restoreAnchor('A')

    // 900 - 0 - (-40) = 940：如果实现记的是 scrollTop，这里会是 640（看到的是别的段落）
    expect(scroller.scrollTop).toBe(940)
  })

  it('锚点行已不存在时回落到保存的 scrollTop', () => {
    const scroller = makeScroller()
    const heights = Array.from({ length: 10 }, () => ROW_H)
    mountRows(scroller, IDS_10, heights)
    const { result } = setup(scroller)

    scroller.scrollTop = 640
    result.current.saveAnchor('A')

    // 消息被删/被合并（db-7 不在了）：没有语义可依，退回兜底值
    mountRows(scroller, ['db-1', 'db-2', 'db-3'], [ROW_H, ROW_H, ROW_H])
    scroller.scrollTop = 0
    result.current.restoreAnchor('A')

    expect(scroller.scrollTop).toBe(640)
  })

  it('保存时视口里一行都没有（空态）→ 恢复同样回落到 scrollTop，不抛错', () => {
    const scroller = makeScroller()
    mountRows(scroller, [], [])
    const { result } = setup(scroller)

    scroller.scrollTop = 0
    result.current.saveAnchor('empty')
    expect(readScrollAnchor('empty')).toEqual({ anchorKey: '', anchorTop: 0, scrollTop: 0 })

    mountRows(scroller, ['db-1'], [ROW_H])
    result.current.restoreAnchor('empty')
    expect(scroller.scrollTop).toBe(0)
  })

  it('两个会话的位置各自独立（切来切去互不覆盖）', () => {
    const scroller = makeScroller()
    const heights = Array.from({ length: 10 }, () => ROW_H)
    mountRows(scroller, IDS_10, heights)
    const { result } = setup(scroller)

    scroller.scrollTop = 300
    result.current.saveAnchor('A')
    scroller.scrollTop = 700
    result.current.saveAnchor('B')

    scroller.scrollTop = 0
    result.current.restoreAnchor('A')
    expect(scroller.scrollTop).toBe(300)

    scroller.scrollTop = 0
    result.current.restoreAnchor('B')
    expect(scroller.scrollTop).toBe(700)
  })
})

describe('useScrollAnchor：无记录 / 入参缺失时不动作', () => {
  it('没有该会话的记录：不动作（位置留给调用方的贴底逻辑）', () => {
    const scroller = makeScroller()
    mountRows(scroller, IDS_10, Array.from({ length: 10 }, () => ROW_H))
    const { result } = setup(scroller)

    scroller.scrollTop = 123
    result.current.restoreAnchor('never-visited')

    expect(scroller.scrollTop).toBe(123)
  })

  it('sessionId 为 null：不写入也不恢复', () => {
    const scroller = makeScroller()
    mountRows(scroller, IDS_10, Array.from({ length: 10 }, () => ROW_H))
    const { result } = setup(scroller)

    scroller.scrollTop = 500
    result.current.saveAnchor(null)
    expect(readScrollAnchor('null')).toBeUndefined()

    scroller.scrollTop = 200
    result.current.restoreAnchor(null)
    expect(scroller.scrollTop).toBe(200)
  })

  it('容器还没挂载（ref 为空）：两个动作都安全空转', () => {
    const { result } = setup(null)
    expect(() => result.current.saveAnchor('A')).not.toThrow()
    expect(() => result.current.restoreAnchor('A')).not.toThrow()
    expect(readScrollAnchor('A')).toBeUndefined()
  })
})

describe('useScrollAnchor：与浏览器原生锚定的冲突', () => {
  it('挂载后滚动容器恒为 overflow-anchor: none（两套锚定不能同时开）', () => {
    const scroller = makeScroller()
    mountRows(scroller, IDS_10, Array.from({ length: 10 }, () => ROW_H))
    const { result } = setup(scroller)

    expect(scroller.style.overflowAnchor).toBe('none')

    // 保存/恢复路径也不能把它改回去
    scroller.scrollTop = 640
    result.current.saveAnchor('A')
    result.current.restoreAnchor('A')
    expect(scroller.style.overflowAnchor).toBe('none')
  })
})

describe('useScrollAnchor：图片/字体二次布局校正', () => {
  it('观察内容容器（不是滚动容器），恢复后校正一次再断开', () => {
    const scroller = makeScroller()
    const heights = Array.from({ length: 10 }, () => ROW_H)
    const wrap = mountRows(scroller, IDS_10, heights)
    const { result } = setup(scroller)

    scroller.scrollTop = 640
    result.current.saveAnchor('A')
    mountRows(scroller, IDS_10, heights)
    scroller.scrollTop = 0
    result.current.restoreAnchor('A')
    expect(scroller.scrollTop).toBe(640)

    const ro = FakeRO.instances.at(-1)!
    // 观察对象必须是内容容器：滚动容器的 border-box 不会因为图片加载而变化
    expect(ro.targets).toEqual([scroller.firstElementChild])
    expect(scroller.firstElementChild).not.toBe(wrap) // 上一轮的 DOM 已被替换

    // 第一次回调是 observe() 的初始通知（尺寸没变 → delta 0）：必须继续观察
    ro.fire()
    expect(ro.disconnected).toBe(false)
    expect(scroller.scrollTop).toBe(640)

    // 图片加载完，上面六行各长高 50px → 锚点行被推下去 300px
    for (let i = 0; i < 6; i++) heights[i] = 150
    ro.fire()

    expect(scroller.scrollTop).toBe(940)
    // 校正只做一次：断开后不会再和用户的滚动抢
    expect(ro.disconnected).toBe(true)
  })

  it('两次回调都没位移 → 收工断开，不长期持有元素', () => {
    const scroller = makeScroller()
    const heights = Array.from({ length: 10 }, () => ROW_H)
    mountRows(scroller, IDS_10, heights)
    const { result } = setup(scroller)

    scroller.scrollTop = 640
    result.current.saveAnchor('A')
    scroller.scrollTop = 0
    result.current.restoreAnchor('A')

    const ro = FakeRO.instances.at(-1)!
    ro.fire()
    ro.fire()
    expect(ro.disconnected).toBe(true)
  })

  it('卸载时断开观察器', () => {
    const scroller = makeScroller()
    const heights = Array.from({ length: 10 }, () => ROW_H)
    mountRows(scroller, IDS_10, heights)
    const { result, unmount } = setup(scroller)

    scroller.scrollTop = 640
    result.current.saveAnchor('A')
    scroller.scrollTop = 0
    result.current.restoreAnchor('A')
    const ro = FakeRO.instances.at(-1)!

    unmount()
    expect(ro.disconnected).toBe(true)
  })

  it('环境没有 ResizeObserver（很老的浏览器）→ 恢复照常生效，只是不校正', () => {
    const scroller = makeScroller()
    const heights = Array.from({ length: 10 }, () => ROW_H)
    mountRows(scroller, IDS_10, heights)
    const { result } = setup(scroller)
    delete (globalThis as unknown as { ResizeObserver?: unknown }).ResizeObserver

    scroller.scrollTop = 640
    result.current.saveAnchor('A')
    scroller.scrollTop = 0
    expect(() => result.current.restoreAnchor('A')).not.toThrow()
    expect(scroller.scrollTop).toBe(640)
  })
})
