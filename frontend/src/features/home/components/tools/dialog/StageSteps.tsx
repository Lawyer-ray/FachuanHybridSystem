import { CheckCircle2, Loader2, XCircle } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * 垂直阶段步进器：处理中弹窗里展示「解析 → 下载 → 匹配 → 重命名 → 通知」走到哪一步。
 * current 之前的算完成，current 行高亮转圈，failedAt 指定的行标红。
 */
export function StageSteps({
  steps,
  current,
  failedAt = null,
}: {
  steps: readonly string[]
  /** 当前进行到的阶段下标（终态时停在最后一眼看到的阶段） */
  current: number
  /** 在哪个阶段失败（有明确失败阶段的状态才传，如 download_failed → 1） */
  failedAt?: number | null
}) {
  return (
    <ol className="flex flex-col gap-[3px]">
      {steps.map((label, i) => {
        const done = i < current
        const active = i === current
        const failed = failedAt === i
        return (
          <li
            key={label}
            className={cn(
              'flex items-center gap-2.5 rounded-[9px] px-2.5 py-[7px] transition-colors',
              active && 'bg-status-blue-bg',
              failed && 'bg-status-red-bg',
            )}
          >
            {failed ? (
              <XCircle className="h-4 w-4 flex-none text-status-red" />
            ) : done ? (
              <CheckCircle2 className="h-4 w-4 flex-none text-status-green" />
            ) : active ? (
              <Loader2 className="h-4 w-4 flex-none animate-spin text-status-blue" />
            ) : (
              <span className="mx-[3px] h-[10px] w-[10px] flex-none rounded-full border-[1.5px] border-muted-foreground/35" />
            )}
            <span
              className={cn(
                'text-[12px]',
                failed
                  ? 'font-semibold text-status-red'
                  : active
                    ? 'font-semibold text-foreground'
                    : done
                      ? 'text-secondary-foreground'
                      : 'text-muted-foreground',
              )}
            >
              {label}
            </span>
            {active && !failed && <span className="ml-auto text-[10.5px] text-muted-foreground">进行中…</span>}
            {failed && <span className="ml-auto text-[10.5px] font-medium text-status-red">失败</span>}
          </li>
        )
      })}
    </ol>
  )
}
