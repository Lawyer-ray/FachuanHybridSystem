import { useEffect, useState } from 'react'

/**
 * 响应式查询：订阅 matchMedia 的 change 事件（只在跨断点时触发一次），
 * 替代「render 时读 window.innerWidth」——后者读的是瞬间值，窗口缩放后不会更新。
 * home（760px 手机抽屉）与 material-prep（1100px 窄屏三栏变抽屉）共用。
 */
export function useMediaQuery(query: string): boolean {
  const [match, setMatch] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const on = () => setMatch(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [query])
  return match
}
