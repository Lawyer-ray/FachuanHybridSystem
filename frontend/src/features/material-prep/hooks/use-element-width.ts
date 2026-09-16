import { useCallback, useEffect, useState } from 'react'

/**
 * 跟踪元素布局宽度（ResizeObserver），用于阅读器列数/页宽的自适应计算。
 * 用 callback ref：元素可能晚于 effect 挂载（详情页加载空态时中栏尚未渲染），
 * 元素一出现就建立测量，避免因 ref 初始为 null 而永久测不到宽。
 */
export function useElementWidth<T extends HTMLElement>() {
  const [width, setWidth] = useState(0)
  const [el, setEl] = useState<T | null>(null)

  useEffect(() => {
    if (!el) return
    const measure = () => setWidth(el.clientWidth)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [el])

  const ref = useCallback(
    (node: T | null) => {
      setEl(node)
    },
    [],
  )

  return [ref, width] as const
}
