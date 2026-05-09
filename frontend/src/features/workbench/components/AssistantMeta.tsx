/** 助手消息底部的元信息（token 用量、模型） */

import type { WorkbenchMessage } from '../types'

export function AssistantMeta({ message }: { message: WorkbenchMessage }) {
  const tokens = message.metadata?.tokens as { prompt?: number; completion?: number; total?: number } | undefined
  const durationMs = message.metadata?.duration_ms as number | undefined

  if (!tokens && !message.llm_model) return null

  return (
    <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground opacity-60">
      {tokens && (
        <span>
          输入 {tokens.prompt ?? 0} / 输出 {tokens.completion ?? 0} / 共 {tokens.total ?? 0} tokens
          {durationMs != null && ` · ${Math.round(durationMs)}ms`}
        </span>
      )}
      {message.llm_model && <span>{message.llm_model}</span>}
    </div>
  )
}
