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
 * ResizeObserver / scroll / resize 订阅只在挂载时建立一次；sel 或列表变化
 * 只触发一次重绘，不重建订阅。sel 用 ref 跟踪，不进订阅 effect 的依赖。
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

  // 订阅：只在挂载时建立一次
  useEffect(() => {
    const ring = ringRef.current
    const wrap = wrapRef.current
    const grid = gridRef.current
    if (!ring || !wrap || !grid) return
    const paint = () => paintRing(grid, wrap, ring, selRef.current)
    const raf = () => requestAnimationFrame(paint)
    raf()
    const ro = new ResizeObserver(raf)
    ro.observe(grid)
    window.addEventListener('scroll', paint, { passive: true })
    window.addEventListener('resize', paint)
    return () => {
      ro.disconnect()
      window.removeEventListener('scroll', paint)
      window.removeEventListener('resize', paint)
    }
  }, [gridRef, wrapRef, ringRef])

  // sel / 列表 / 页签变化 → 只重绘一次（不重订阅）
  useEffect(() => {
    const ring = ringRef.current
    const wrap = wrapRef.current
    const grid = gridRef.current
    if (!ring || !wrap || !grid) return
    requestAnimationFrame(() => paintRing(grid, wrap, ring, sel))
  }, [sel, visible, tab, gridRef, wrapRef, ringRef])
}
