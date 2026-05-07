/** 上下文用量指示器 */

import { useEffect, useRef } from 'react'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'
import { useContextUsage, formatTokens } from '../hooks/use-context-usage'
import { toast } from 'sonner'

export function ContextUsageBar() {
  const { percent, usedTokens, contextWindow, messageCount } = useContextUsage()
  const prevPercentRef = useRef(0)

  // 溢出预警
  useEffect(() => {
    if (percent >= 90 && prevPercentRef.current < 90) {
      toast.error('上下文窗口即将用完，建议新建会话', { duration: 8000 })
    } else if (percent >= 80 && prevPercentRef.current < 80) {
      toast.warning('上下文窗口已使用 80%，建议新建会话', { duration: 5000 })
    }
    prevPercentRef.current = percent
  }, [percent])

  if (!contextWindow || messageCount === 0) return null

  const colorClass =
    percent < 50
      ? 'text-green-600 dark:text-green-400'
      : percent < 80
        ? 'text-yellow-600 dark:text-yellow-400'
        : 'text-red-600 dark:text-red-400'

  return (
    <div className="hidden md:flex items-center gap-2 min-w-[140px]">
      <Progress
        value={percent}
        className={cn(
          'h-1.5 flex-1',
          percent < 50
            ? '[&>[data-slot=progress-indicator]]:bg-green-500'
            : percent < 80
              ? '[&>[data-slot=progress-indicator]]:bg-yellow-500'
              : '[&>[data-slot=progress-indicator]]:bg-red-500',
        )}
      />
      <span className={cn('text-[11px] tabular-nums whitespace-nowrap', colorClass)}>
        {formatTokens(usedTokens)} / {formatTokens(contextWindow)}
      </span>
    </div>
  )
}
