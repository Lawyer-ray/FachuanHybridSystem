/** 消息操作按钮：反馈（👍👎）+ hover 操作（复制/引用/重新生成） */

import { Copy, RefreshCw, ThumbsUp, ThumbsDown, Quote } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { copyToClipboard } from '@/lib/clipboard'
import { useWorkbenchStore } from '../stores/workbench-store'
import type { WorkbenchMessage } from '../types'

/** 消息反馈按钮（👍👎） */
export function FeedbackButtons({ message }: { message: WorkbenchMessage }) {
  const submitFeedback = useWorkbenchStore((s) => s.submitFeedback)
  const isStreaming = useWorkbenchStore((s) => s.isStreaming)
  const feedback = message.metadata?.feedback as { rating?: string } | undefined
  const currentRating = feedback?.rating

  if (isStreaming) return null

  return (
    <div className="mt-1 flex items-center gap-1">
      <button
        onClick={() => submitFeedback(message.id, 'good')}
        className={cn(
          'flex items-center justify-center rounded p-1 transition-colors',
          currentRating === 'good'
            ? 'text-green-500 bg-green-500/10'
            : 'text-muted-foreground hover:text-green-500 hover:bg-green-500/10',
        )}
        title="有帮助"
      >
        <ThumbsUp className="size-3.5" />
      </button>
      <button
        onClick={() => submitFeedback(message.id, 'bad')}
        className={cn(
          'flex items-center justify-center rounded p-1 transition-colors',
          currentRating === 'bad'
            ? 'text-destructive bg-destructive/10'
            : 'text-muted-foreground hover:text-destructive hover:bg-destructive/10',
        )}
        title="没帮助"
      >
        <ThumbsDown className="size-3.5" />
      </button>
    </div>
  )
}

/** 助手消息 hover 操作按钮（复制 + 引用 + 重新生成） */
export function MessageActions({ message }: { message: WorkbenchMessage }) {
  const sendMessage = useWorkbenchStore((s) => s.sendMessage)
  const messages = useWorkbenchStore((s) => s.messages)
  const isStreaming = useWorkbenchStore((s) => s.isStreaming)
  const setQuotedContent = useWorkbenchStore((s) => s.setQuotedContent)

  const handleCopy = () => copyToClipboard(message.content)

  const handleQuote = () => {
    const preview = message.content.length > 200 ? message.content.slice(0, 200) + '...' : message.content
    setQuotedContent(preview)
    toast.success('已引用，可在输入框中查看')
  }

  const handleRegenerate = () => {
    if (isStreaming) return
    const idx = messages.findIndex((m) => m.id === message.id)
    if (idx < 0) return
    for (let i = idx - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        sendMessage(messages[i].content)
        return
      }
    }
  }

  return (
    <div className="absolute -top-2 right-2 hidden group-hover:flex items-center gap-1 rounded-md border bg-background p-0.5 shadow-sm">
      <button
        onClick={handleCopy}
        className="flex items-center justify-center rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
        title="复制"
      >
        <Copy className="size-3.5" />
      </button>
      <button
        onClick={handleQuote}
        className="flex items-center justify-center rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
        title="引用"
      >
        <Quote className="size-3.5" />
      </button>
      <button
        onClick={handleRegenerate}
        disabled={isStreaming}
        className="flex items-center justify-center rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50"
        title="重新生成"
      >
        <RefreshCw className="size-3.5" />
      </button>
    </div>
  )
}
