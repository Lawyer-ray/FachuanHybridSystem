// @vitest-environment jsdom
/**
 * useElementWidth 单测（jsdom + ResizeObserver 桩）。
 *
 * 覆盖：callback ref 挂载即建立测量（晚于首帧挂载也测得到）、
 * ResizeObserver 回调更新宽度、元素卸载断开观察、null ref（空态）不建观察。
 * jsdom 的 clientWidth 恒 0，用可变 getter 注入受控宽度。
 */
import { useCallback, useEffect, useState } from 'react'
import { act, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useElementWidth } from './use-element-width'

/** ResizeObserver 桩：登记回调与 observed 元素 */
function installResizeObserver() {
  const instances: Array<{ cb: ResizeObserverCallback; els: Set<Element> }> = []
  class FakeRO {
    cb: ResizeObserverCallback
    els = new Set<Element>()
    constructor(cb: ResizeObserverCallback) {
      this.cb = cb
      instances.push(this as unknown as { cb: ResizeObserverCallback; els: Set<Element> })
    }
    observe(el: Element) {
      this.els.add(el)
    }
    unobserve(el: Element) {
      this.els.delete(el)
    }
    disconnect() {
      this.els.clear()
    }
  }
  vi.stubGlobal('ResizeObserver', FakeRO)
  return { instances }
}

/** harness：clientWidth 由外部变量控制；最新宽度回抛给用例。
 *  ref 回调保持引用稳定（useCallback），避免 React 每次 render 的
 *  ref(null)/ref(node) 拆装循环干扰被测 hook。 */
function Harness({ widthRef, onWidth }: { widthRef: { value: number }; onWidth: (w: number) => void }) {
  const [ref, width] = useElementWidth<HTMLDivElement>()
  const stableRef = useCallback(
    (node: HTMLDivElement | null) => {
      if (node) Object.defineProperty(node, 'clientWidth', { get: () => widthRef.value, configurable: true })
      ref(node)
    },
    [ref, widthRef],
  )
  onWidth(width)
  return <div ref={stableRef} />
}

/** 空态 harness：ref 只收 null（模拟详情未加载、中栏未渲染） */
function NullRefHarness() {
  const [ref, width] = useElementWidth<HTMLDivElement>()
  useEffect(() => {
    ref(null)
  }, [ref])
  return <span data-testid="w">{width}</span>
}

/** 稍后挂载 harness：先空渲染、下一帧才挂真实元素（callback ref 的存在意义） */
function LateMountHarness({ widthRef, onWidth }: { widthRef: { value: number }; onWidth: (w: number) => void }) {
  const [mounted, setMounted] = useState(false)
  const [ref, width] = useElementWidth<HTMLDivElement>()
  const stableRef = useCallback(
    (node: HTMLDivElement | null) => {
      if (node) Object.defineProperty(node, 'clientWidth', { get: () => widthRef.value, configurable: true })
      ref(node)
    },
    [ref, widthRef],
  )
  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 0)
    return () => clearTimeout(t)
  }, [])
  onWidth(width)
  return mounted ? <div ref={stableRef} /> : null
}

describe('useElementWidth', () => {
  let ro: ReturnType<typeof installResizeObserver>

  beforeEach(() => {
    ro = installResizeObserver()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('元素挂载：立即测量一次并开始观察（宽度取 clientWidth）', () => {
    const widthRef = { value: 333 }
    const widths: number[] = []
    const { container } = render(<Harness widthRef={widthRef} onWidth={(w) => widths.push(w)} />)

    // 序列：初始 0 → setEl 触发一次重渲（仍 0）→ effect 测量 333
    expect(widths[0]).toBe(0)
    expect(widths.at(-1)).toBe(333)
    const el = container.querySelector('div')!
    expect(ro.instances).toHaveLength(1)
    expect(ro.instances[0]!.els.has(el)).toBe(true)
  })

  it('ResizeObserver 回调 → 宽度更新；卸载 → disconnect 清空观察', () => {
    const widthRef = { value: 100 }
    let reported = -1
    const { unmount } = render(<Harness widthRef={widthRef} onWidth={(w) => (reported = w)} />)
    expect(reported).toBe(100)

    widthRef.value = 240
    const inst = ro.instances.at(-1)!
    act(() => {
      inst.cb([], inst as unknown as ResizeObserver)
    })
    expect(reported).toBe(240)

    unmount()
    expect(inst.els.size).toBe(0)
  })

  it('空态（ref 收到 null）：不建 ResizeObserver、宽度保持 0', () => {
    const { getByTestId } = render(<NullRefHarness />)
    expect(getByTestId('w').textContent).toBe('0')
    expect(ro.instances).toHaveLength(0)
  })

  it('元素晚于首帧挂载（详情加载后中栏才出现）：挂载瞬间即测到宽度', async () => {
    const widthRef = { value: 555 }
    let reported = -1
    render(<LateMountHarness widthRef={widthRef} onWidth={(w) => (reported = w)} />)
    expect(reported).toBe(0)
    await new Promise((r) => setTimeout(r, 10))
    expect(reported).toBe(555)
    expect(ro.instances).toHaveLength(1)
  })
})
