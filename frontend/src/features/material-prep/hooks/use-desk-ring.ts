import { useEffect } from 'react'

/**
 * ring 高亮跟随选中卡片：给选中的材料包卡片画一个跟随定位的高亮框。
 * 高频 UI 状态用 ref + 直接 DOM 操作绕过 React 协调（见规范「性能陷阱」）。
 *
 * @param sel    当前选中序号
 * @param dep    ring 需要重算的依赖（列表 / 页签变化）
 * @param gridRef PackGrid 的网格容器 ref（卡片带 data-pack-idx）
 */
export function useDeskRing(params: {
  sel: number
  dep: unknown
  gridRef: React.RefObject<HTMLDivElement | null>
  wrapRef: React.RefObject<HTMLDivElement | null>
  ringRef: React.RefObject<HTMLDivElement | null>
}) {
  const { sel, dep, gridRef, wrapRef, ringRef } = params

  useEffect(() => {
    const ring = ringRef.current
    const wrap = wrapRef.current
    const grid = gridRef.current
    if (!ring || !wrap || !grid) return
    const paint = () => {
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sel, dep])
}
