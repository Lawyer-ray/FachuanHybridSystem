import { useEffect, useState } from 'react'

/** 服务端 / 纯逻辑测试（node 环境）里没有 window.matchMedia：不读它，一律当不匹配。
 *  与 use-element-width / use-today 同一口径——惰性初始化里直接读 window 会在
 *  node 环境抛 ReferenceError，而不是被 ErrorBoundary 兜住。 */
function matches(query: string): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia(query).matches
}

/**
 * 响应式查询：订阅 matchMedia 的 change 事件（只在跨断点时触发一次），
 * 替代「render 时读 window.innerWidth」——后者读的是瞬间值，窗口缩放后不会更新。
 * home（760px 手机抽屉）与 material-prep（1100px 窄屏三栏变抽屉）共用。
 */
export function useMediaQuery(query: string): boolean {
  const [match, setMatch] = useState(() => matches(query))
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const mq = window.matchMedia(query)
    const on = () => setMatch(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [query])
  return match
}
