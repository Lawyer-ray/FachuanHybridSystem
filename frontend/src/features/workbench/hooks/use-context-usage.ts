/** 上下文用量计算 hook */

import { useMemo } from 'react'
import { useWorkbenchStore } from '../stores/workbench-store'
import type { WorkbenchMessage } from '../types'

/** 估算文本 token 数（与后端 _estimate_tokens 逻辑一致） */
export function estimateTokens(text: string): number {
  if (!text) return 0
  let chinese = 0
  let other = 0
  for (const ch of text) {
    const code = ch.charCodeAt(0)
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
export function estimateMessagesTokens(messages: WorkbenchMessage[]): number {
  let total = 0
  for (const msg of messages) {
    if (msg.content) {
      total += estimateTokens(msg.content)
    }
  }
  return total
}

/** 格式化 token 数（大数显示 K） */
export function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return String(n)
}

/** 上下文用量 hook */
export function useContextUsage() {
  const messages = useWorkbenchStore((s) => s.messages)
  const models = useWorkbenchStore((s) => s.models)
  const selectedModel = useWorkbenchStore((s) => s.selectedModel)

  const contextWindow = useMemo(() => {
    const model = models.find((m) => m.id === (selectedModel || models[0]?.id))
    return model?.context_window ?? 0
  }, [models, selectedModel])

  const usedTokens = useMemo(() => estimateMessagesTokens(messages), [messages])

  const percent = contextWindow > 0
    ? Math.min(100, Math.round((usedTokens / contextWindow) * 100))
    : 0

  return { percent, usedTokens, contextWindow, messageCount: messages.length }
}
