import { useEffect, useState } from 'react'

/**
 * 今天（本地零点）。跨零点或从后台切回时重算，避免长开页面（律师工作台常整夜不关）
 * 的「今日」口径冻结在昨天：日历今天高亮、今日统计、今日到期红点都依赖它。
 *
 * 返回值做引用稳定：日期没变时保持同一 Date 实例，下游 useMemo/查询参数不会无谓失效。
 */
export function useToday(): Date {
  const [today, setToday] = useState(() => midnight(new Date()))

  useEffect(() => {
    const recheck = () => setToday((prev) => {
      const next = midnight(new Date())
      return prev.getTime() === next.getTime() ? prev : next
    })
    const timer = window.setInterval(recheck, 60_000)
    document.addEventListener('visibilitychange', recheck)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', recheck)
    }
  }, [])

  return today
}

function midnight(d: Date): Date {
  const copy = new Date(d)
  copy.setHours(0, 0, 0, 0)
  return copy
}
