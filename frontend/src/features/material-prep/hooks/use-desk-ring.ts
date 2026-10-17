import { useEffect, useRef } from 'react'
import type { InboxMessage, PackStatus } from '../types'
/** 把高亮框定位到第 sel 张卡片（读 DOM，绕过 React 协调） */
function paintRing(
  grid: HTMLDivElement,
  wrap: HTMLDivElement,
  ring: HTMLDivElement,
  sel: number,
): void {
  const cards = grid.querySelectorAll<HTMLElement>('[data-pack-idx]')
  if (!cards.length) {
    ring.classList.remove('on')
    return
  }
  const c = cards[Math.min(sel, cards.length - 1)]
  if (!c) {
    ring.classList.remove('on')
    return
  }
  const wr = wrap.getBoundingClientRect()
  const cr = c.getBoundingClientRect()
  ring.style.width = `${cr.width}px`
  ring.style.height = `${cr.height}px`
  ring.style.transform = `translate(${cr.left - wr.left}px, ${cr.top - wr.top}px)`
  ring.classList.add('on')
}

/**
 * ring 高亮跟随选中卡片。
 * 高频 UI 状态用 ref + 直接 DOM 操作绕过 React 协调（见规范「性能陷阱」）。
 *
 * ResizeObserver / scroll / resize 订阅在「网格节点出现」时建立一次，之后
 * sel 或列表变化只触发重绘、不重建订阅。sel 用 ref 跟踪，不进订阅 effect 的依赖。
 *
 * 为什么不能只在挂载时订阅：DeskPage 在 isLoading 期间渲染骨架、不渲染 PackGrid，
 * 首次挂载拿不到 grid/ring 节点，effect 提前返回后就再也不会跑——resize / scroll
 * 全部没挂上，ring 只在列表变化时画一次，窗口一拉伸就和卡片错位（修复前实测：
 * 1400→640 宽，框比卡窄 280px）。用 hasCards 作为「节点已就绪」的信号重新订阅。
 */
export function useDeskRing(params: {
  sel: number
  visible: InboxMessage[]
  tab: PackStatus
  gridRef: React.RefObject<HTMLDivElement | null>
  wrapRef: React.RefObject<HTMLDivElement | null>
  ringRef: React.RefObject<HTMLDivElement | null>
}) {
  const { sel, visible, tab, gridRef, wrapRef, ringRef } = params
  // 用 ref 存最新 sel，供订阅 effect 内的 paint 读取。
  // 注意：写 ref 放在 effect 里，不放在 render 主体（React 19 的 react-hooks/refs 规则）
  const selRef = useRef(sel)
  useEffect(() => {
    selRef.current = sel
  }, [sel])

  // 有卡片才需要 ring；也是 PackGrid（grid / ring 节点）已渲染的信号
  const hasCards = visible.length > 0

  // 订阅：节点就绪后建立一次；卡片从有到无再到有才会重建
  useEffect(() => {
    if (!hasCards) return
    const ring = ringRef.current
    const wrap = wrapRef.current
    const grid = gridRef.current
    if (!ring || !wrap || !grid) return
    const paint = () => paintRing(grid, wrap, ring, selRef.current)
    requestAnimationFrame(paint)
    // RO 回调本就在布局之后触发，直接重绘；再包一层 rAF 只会让框在拖拽窗口时
    // 慢一帧。ring 挂在 wrap 不在被观察的 grid 里，写它的样式不会触发 RO 循环。
    // 环境没有 ResizeObserver（jsdom）时退化为只靠 window resize
    const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(paint)
    ro?.observe(grid)
    window.addEventListener('scroll', paint, { passive: true })
    window.addEventListener('resize', paint)
    // 卡片自身的过渡 / 动画结束再对一次：resize 触发的那次重绘可能量到卡片
    // 尺寸过渡的中间帧（此后再无 resize 事件）。两类事件都会从卡片冒泡到 grid
    grid.addEventListener('transitionend', paint)
    grid.addEventListener('animationend', paint)
    return () => {
      ro?.disconnect()
      window.removeEventListener('scroll', paint)
      window.removeEventListener('resize', paint)
      grid.removeEventListener('transitionend', paint)
      grid.removeEventListener('animationend', paint)
    }
  }, [hasCards, gridRef, wrapRef, ringRef])

  // sel / 列表 / 页签变化 → 只重绘一次（不重订阅）
  useEffect(() => {
    const ring = ringRef.current
    const wrap = wrapRef.current
    const grid = gridRef.current
    if (!ring || !wrap || !grid) return
    requestAnimationFrame(() => paintRing(grid, wrap, ring, sel))
  }, [sel, visible, tab, gridRef, wrapRef, ringRef])
}
