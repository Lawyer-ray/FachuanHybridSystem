import { useEffect, useLayoutEffect, useRef } from 'react'

import { useReader } from '../../store'
import { ZOOM_MAX, ZOOM_MIN } from './ui'

/**
 * ⌘ / Ctrl + 滚轮缩放画布（触控板双指捏合也走这里：浏览器把捏合派成带 ctrlKey 的 wheel）。
 *
 * 必须用原生 `passive: false` 监听：React 17+ 把 onWheel 注册为 passive，回调里
 * preventDefault 无效，拦不住浏览器自己的整页缩放。缩放前记下指针在内容里的相对
 * 位置，布局按新页宽更新后把滚动条拨回去，让指针下的那块页面留在原地。
 */
export function useWheelZoom(el: HTMLElement | null, zoom: number) {
  const anchor = useRef<{ x: number; y: number; rx: number; ry: number } | null>(null)

  useEffect(() => {
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return
      e.preventDefault()
      const cur = useReader.getState().zoom
      // 指数步进：鼠标滚一格 deltaY≈100 → ×0.78 / ×1.28；触控板捏合每帧只有几个单位，连续平滑
      const next = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, cur * Math.exp(-e.deltaY * 0.0025)))
      if (next === cur) return
      const r = el.getBoundingClientRect()
      const x = e.clientX - r.left
      const y = e.clientY - r.top
      anchor.current = {
        x,
        y,
        rx: el.scrollWidth ? (el.scrollLeft + x) / el.scrollWidth : 0,
        ry: el.scrollHeight ? (el.scrollTop + y) / el.scrollHeight : 0,
      }
      useReader.getState().setZoom(next)
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [el])

  // 新页宽落地后（Flow 同步按 zoom 算 --mp-cw，已加载的页图 width:100% 随之改高）拨回滚动条
  useLayoutEffect(() => {
    const a = anchor.current
    if (!el || !a) return
    anchor.current = null
    el.scrollLeft = a.rx * el.scrollWidth - a.x
    el.scrollTop = a.ry * el.scrollHeight - a.y
  }, [el, zoom])
}
