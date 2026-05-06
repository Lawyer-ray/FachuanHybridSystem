/** 上下文用量指示器 */

import { useMemo } from 'react'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'
import { useWorkbenchStore } from '../stores/workbench-store'
import type { WorkbenchMessage } from '../types'

/** 估算文本 token 数（与后端 _estimate_tokens 逻辑一致） */
function estimateTokens(text: string): number {
  if (!text) return 0
  let chinese = 0
  let other = 0
  for (const ch of text) {
    const code = ch.charCodeAt(0)
    // 中文字符范围：CJK Unified Ideographs 基本区 + 扩展A
    if (
      (code >= 0x4e00 && code <= 0x9fff) ||
      (code >= 0x3400 && code <= 0x4dbf)
    ) {
      chinese++
    } else {
      other++
    }
  }
  return Math.max(1, Math.round(chinese * 1.5 + other * 0.3))
}

/** 计算消息列表的累计 token 数 */
function estimateMessagesTokens(messages: WorkbenchMessage[]): number {
  let total = 0
  for (const msg of messages) {
    if (msg.content) {
      total += estimateTokens(msg.content)
    }
  }
  return total
}

/** 格式化 token 数（大数显示 K） */
function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return String(n)
}

export function ContextUsageBar() {
  const messages = useWorkbenchStore((s) => s.messages)
  const models = useWorkbenchStore((s) => s.models)
  const selectedModel = useWorkbenchStore((s) => s.selectedModel)

  const contextWindow = useMemo(() => {
    const model = models.find((m) => m.id === (selectedModel || models[0]?.id))
    return model?.context_window ?? 0
  }, [models, selectedModel])

  const usedTokens = useMemo(() => estimateMessagesTokens(messages), [messages])

  // 无上下文窗口信息或无消息时不显示
  if (!contextWindow || messages.length === 0) return null

  const percent = Math.min(100, Math.round((usedTokens / contextWindow) * 100))
  const colorClass =
    percent < 50
      ? 'text-green-600 dark:text-green-400'
      : percent < 80
        ? 'text-yellow-600 dark:text-yellow-400'
        : 'text-red-600 dark:text-red-400'

  return (
    <div className="flex items-center gap-2 min-w-[140px]">
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
