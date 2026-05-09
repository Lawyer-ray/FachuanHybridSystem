/** 流式消息气泡组件 */

import { Bot, ArrowRight, CheckCircle2, XCircle, Loader2, AlertCircle } from 'lucide-react'
import { useWorkbenchStore } from '../stores/workbench-store'
import type { StreamingMessage, ToolCallState } from '../types'
import { MarkdownContent } from './MarkdownContent'

/** 工具调用状态指示器 */
function ToolCallIndicator({ toolCall }: { toolCall: ToolCallState }) {
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground bg-background/50 rounded px-2 py-1.5">
      {toolCall.status === 'running' && <Loader2 className="size-3 animate-spin" />}
      {toolCall.status === 'success' && <CheckCircle2 className="size-3 text-green-500" />}
      {toolCall.status === 'error' && <XCircle className="size-3 text-destructive" />}
      {toolCall.status === 'pending' && <Loader2 className="size-3 opacity-30" />}
      <span className="font-medium">{toolCall.name}</span>
    </div>
  )
}

/** Agent 切换徽章 */
function HandoffBadge({ from, to }: { from: string; to: string }) {
  return (
    <div className="flex items-center gap-1.5 text-[11px] bg-blue-500/10 text-blue-600 dark:text-blue-400 rounded-full px-2 py-0.5">
      <ArrowRight className="size-3" />
      <span>{from}</span>
      <ArrowRight className="size-3" />
      <span>{to}</span>
    </div>
  )
}

/** 流式消息气泡 */
export function StreamingBubble({ message }: { message: StreamingMessage }) {
  const reconnecting = useWorkbenchStore((s) => s.reconnecting)

  return (
    <div className="flex gap-2 md:gap-3 justify-start">
      <div className="flex size-6 md:size-8 shrink-0 items-center justify-center rounded-full bg-primary/10">
        <Bot className="size-4 text-primary animate-pulse" />
      </div>
      <div className="max-w-[85%] md:max-w-[75%] min-w-0 rounded-lg bg-muted px-4 py-2.5 text-sm space-y-2">
        {reconnecting && (
          <div className="flex items-center gap-2 rounded-md bg-amber-500/10 px-3 py-1.5 text-xs text-amber-600 dark:text-amber-400">
            <Loader2 className="size-3 animate-spin" />
            <span>连接中断，正在重连...</span>
          </div>
        )}

        {message.currentActivity && !reconnecting && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="size-3 animate-spin" />
            <span>{message.currentActivity}</span>
          </div>
        )}

        {message.handoffs.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {message.handoffs.map((h, i) => (
              <HandoffBadge key={i} from={h.from} to={h.to} />
            ))}
          </div>
        )}

        {message.toolCalls.length > 0 && (
          <div className="space-y-1">
            {message.toolCalls.map((tc) => (
              <ToolCallIndicator key={tc.toolCallId} toolCall={tc} />
            ))}
          </div>
        )}

        {message.error && (
          <div className="flex items-start gap-2 rounded-md bg-destructive/10 px-3 py-2 text-destructive text-xs">
            <AlertCircle className="size-3.5 shrink-0 mt-0.5" />
            <span>{message.error}</span>
          </div>
        )}

        {message.content && (
          <MarkdownContent content={message.content} />
        )}

        <span className="inline-block w-2 h-4 bg-primary/50 animate-pulse ml-0.5" />

        {message.model && (
          <div className="text-[10px] text-muted-foreground">{message.model}</div>
        )}
      </div>
    </div>
  )
}
