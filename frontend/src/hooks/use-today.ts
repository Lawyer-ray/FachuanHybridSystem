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
    const recheck = () => {
      setToday((prev) => {
        const next = midnight(new Date())
        return prev.getTime() === next.getTime() ? prev : next
      })
    }
    // 精确排到下一个零点，而不是常驻 60s 轮询：整夜不关的工作台原本要空转
    // 1440 次只为发现「日期没变」。定时器一次只跑一趟，到点重算后重新排；
    // 分段排也顺带扛住了休眠/系统改时间把一次性长定时器错开的问题。
    let timer: number | undefined
    const schedule = () => {
      window.clearTimeout(timer)
      timer = window.setTimeout(arm, msUntilMidnight(new Date()))
    }
    const arm = () => {
      recheck()
      schedule()
    }
    schedule()
    // 后台切回可能已跨零点（标签页休眠时定时器会被节流甚至暂停），立即补一次
    const onVisible = () => {
      recheck()
      schedule()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [])

  return today
}

/** 到本地下一个零点的毫秒数（至少 1，避免 0 毫秒定时器自旋） */
export function msUntilMidnight(now: Date): number {
  const next = midnight(now)
  next.setDate(next.getDate() + 1)
  // 夏令时切换那天零点间隔不是 24h，用两个 Date 相减而不是写死毫秒数
  return Math.max(1, next.getTime() - now.getTime())
}

function midnight(d: Date): Date {
  const copy = new Date(d)
  copy.setHours(0, 0, 0, 0)
  return copy
}
