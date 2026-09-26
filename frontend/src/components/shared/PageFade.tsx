import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useLocation } from 'react-router'

/**
 * 页面内容切换时的入场过渡。
 *
 * navbar 是全站共用组件，在各路由下完全一样，所以视觉上是稳定的锚点；
 * 变的只是它下面的内容区。以前内容是「瞬间替换」，观感很生硬。
 *
 * 实现要点：
 * - 用 CSS animation（而非 transition）：同一个渲染周期里连续改状态时，
 *   transition 可能被浏览器跳过（实测过 transform 全程是 none），
 *   而 animation 由 class 挂载触发，稳定可靠。
 * - 用 location.key 做身份标识：同一路径内的变化（例如打开某个
 *   material-prep/:id）不会重放动画，只有真正换了页面才播一次。
 * - 首次挂载不播，否则进站点会白闪一下。
 */
export function PageFade({ children }: { children: ReactNode }) {
  const { pathname, key } = useLocation()
  const [runId, setRunId] = useState(0)
  const firstRun = useRef(true)

  useEffect(() => {
    if (firstRun.current) {
      firstRun.current = false
      return
    }
    // 换个 runId 让下面的 key 变化，从而重新挂载动画元素、重放 animation
    setRunId((n) => n + 1)
  }, [pathname, key])

  return (
    // key 变化 → 元素重新挂载 → animation 从头播放
    <div key={runId} className="app-page-enter">
      {children}
    </div>
  )
}
