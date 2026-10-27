import { useCallback, useEffect, useState } from 'react'

/**
 * 跟踪元素布局宽度（ResizeObserver）。
 *
 * 为什么需要它：视口媒体查询（matchMedia / Tailwind 断点）量不到 AI 助手
 * 并排让位、分栏挤占后的**容器净宽**——布局断点要看「这块区域自己多宽」
 * 时用它（首页日历密度、阅读器窄屏形态与列数）。
 *
 * 用 callback ref：元素可能晚于 effect 挂载（详情页加载空态时中栏尚未渲染），
 * 元素一出现就建立测量，避免因 ref 初始为 null 而永久测不到宽。
 * jsdom 无 ResizeObserver：跳过观察、只保留挂载瞬间的同步测量（恒 0），
 * 让不装桩的组件测试不必每个文件都 stub。
 */
export function useElementWidth<T extends HTMLElement>() {
  const [width, setWidth] = useState(0)
  const [el, setEl] = useState<T | null>(null)

  useEffect(() => {
    if (!el) return
    const measure = () => setWidth(el.clientWidth)
    measure()
    if (typeof ResizeObserver === 'undefined') return
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

  // 第三项把元素本身也交出去：需要挂原生监听（如 passive:false 的 wheel）的调用方用
  return [ref, width, el] as const
}
