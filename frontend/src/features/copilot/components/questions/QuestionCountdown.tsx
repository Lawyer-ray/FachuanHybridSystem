/**
 * 提问卡的倒计时徽标。
 *
 * 语义与审批**刻意不同**（见 backend/apps/agent/services/question.py 的模块注释）：
 * 审批超时 = 拒绝（fail-closed），提问超时 = 模型按假设继续（不阻断）。
 * 所以到点不是「失效」，而是「本轮已继续，仍可补答」——文案必须说清楚，
 * 否则律师会以为自己错过了、答案送不到。
 */

import { useEffect, useState } from 'react'
import { Clock } from 'lucide-react'

import { formatCountdown } from '../../domain'

/** 剩余秒数（渲染期不读 Date.now，保持纯渲染：只在 state 初始化与定时器里算） */
function remaining(timeoutSeconds: number, receivedAt: number): number {
  return Math.max(0, timeoutSeconds - Math.floor((Date.now() - receivedAt) / 1000))
}

export function QuestionCountdown({
  timeoutSeconds,
  receivedAt,
  frozen,
}: {
  timeoutSeconds: number
  receivedAt: number
  /** 已提交/已跳过：不再计时也不提示「已继续」 */
  frozen?: boolean
}) {
  const [remain, setRemain] = useState(() => remaining(timeoutSeconds, receivedAt))

  useEffect(() => {
    // frozen：本组件已 return null，再每秒 setState 只会触发一轮空渲染（与
    // 「到点就停表」同一个意图）——干脆不建表。首帧的 remain 已由 useState
    // 初始化器算过，不需要在 effect 首行再算一次。
    if (frozen) return
    const timer = setInterval(() => {
      const next = remaining(timeoutSeconds, receivedAt)
      setRemain(next)
      // 到点就停表：之后「已继续」是静态文案，不需要每秒重渲染
      if (next <= 0) clearInterval(timer)
    }, 1000)
    return () => clearInterval(timer)
  }, [timeoutSeconds, receivedAt, frozen])

  if (frozen) return null

  if (remain <= 0) {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-amber-600 dark:text-amber-500">
        <Clock className="size-3" aria-hidden />
        本轮已继续，仍可补答
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground tabular-nums">
      <Clock className="size-3" aria-hidden />
      {formatCountdown(remain)} 后按假设继续
    </span>
  )
}
