import { Fragment } from 'react'
import { CheckCircle2, Loader2, XCircle } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * 横向紧凑进度条：终态弹窗（人工分配 / 失败）里替代垂直步进器——
 * 垂直版要占 300px+，会把操作区挤到折叠线以下；横向一行动态收进 ~26px。
 */
export function StageStrip({
  steps,
  current,
  failedAt = null,
}: {
  steps: readonly string[]
  current: number
  failedAt?: number | null
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-1 gap-y-1">
      {steps.map((label, i) => {
        const done = i < current
        const active = i === current
        const failed = failedAt === i
        return (
          <Fragment key={label}>
            {i > 0 && <span className="mx-0.5 h-px w-3 flex-none bg-border" aria-hidden />}
            <span
              className={cn(
                'flex items-center gap-1 text-[10.5px] leading-none',
                failed
                  ? 'font-semibold text-status-red'
                  : active
                    ? 'font-semibold text-status-blue'
                    : done
                      ? 'text-secondary-foreground'
                      : 'text-muted-foreground',
              )}
            >
              {failed ? (
                <XCircle className="h-3.5 w-3.5" />
              ) : done ? (
                <CheckCircle2 className="h-3.5 w-3.5 text-status-green" />
              ) : active ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <span className="mx-[2px] h-[7px] w-[7px] rounded-full border-[1.5px] border-muted-foreground/40" />
              )}
              {label}
            </span>
          </Fragment>
        )
      })}
    </div>
  )
}
