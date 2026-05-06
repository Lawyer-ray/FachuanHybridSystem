/** 消息气泡组件 */

import { useState, useRef, useEffect, useCallback } from 'react'
import {
  Bot,
  User,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  XCircle,
  Loader2,
  ArrowRight,
  Copy,
  RefreshCw,
  Pencil,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { Textarea } from '@/components/ui/textarea'
import { useWorkbenchStore } from '../stores/workbench-store'
import type { WorkbenchMessage, StreamingMessage, ToolCallState } from '../types'

interface MessageBubbleProps {
  message: WorkbenchMessage
  toolCalls?: WorkbenchMessage[]
}

export function MessageBubble({ message, toolCalls }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const isSystem = message.role === 'system'

  return (
    <div className={cn('flex gap-3', isUser ? 'justify-end' : 'justify-start')}>
      {!isUser && (
        <div
          className={cn(
            'flex size-8 shrink-0 items-center justify-center rounded-full',
            isSystem ? 'bg-destructive/10' : 'bg-primary/10',
          )}
        >
          {isSystem ? (
            <AlertCircle className="size-4 text-destructive" />
          ) : (
            <Bot className="size-4 text-primary" />
          )}
        </div>
      )}

      <div
        className={cn(
          'group relative max-w-[80%] rounded-lg px-4 py-2.5 text-sm',
          isUser
            ? 'bg-primary text-primary-foreground'
            : isSystem
              ? 'bg-destructive/10 text-destructive'
              : 'bg-muted',
        )}
      >
        {isUser ? (
          <UserMessageContent message={message} />
        ) : (
          <MarkdownContent content={message.content} isSystem={isSystem} />
        )}

        {/* 内联工具调用 */}
        {toolCalls && toolCalls.length > 0 && (
          <InlineToolCalls toolCalls={toolCalls} />
        )}

        {/* 助手消息：token 用量 + 模型标签 */}
        {!isUser && !isSystem && (
          <AssistantMeta message={message} />
        )}

        {/* 助手消息：hover 操作按钮 */}
        {!isUser && !isSystem && (
          <MessageActions message={message} />
        )}
      </div>

      {isUser && (
        <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary">
          <User className="size-4 text-primary-foreground" />
        </div>
      )}
    </div>
  )
}

/** 用户消息内容（支持编辑） */
function UserMessageContent({ message }: { message: WorkbenchMessage }) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(message.content)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const editAndResend = useWorkbenchStore((s) => s.editAndResend)
  const isStreaming = useWorkbenchStore((s) => s.isStreaming)

  useEffect(() => {
    if (editing) {
      textareaRef.current?.focus()
      textareaRef.current?.select()
    }
  }, [editing])

  const handleSave = useCallback(() => {
    const trimmed = value.trim()
    if (trimmed && trimmed !== message.content) {
      editAndResend(message.id, trimmed)
    }
    setEditing(false)
  }, [value, message.content, message.id, editAndResend])

  if (editing) {
    return (
      <div className="space-y-2">
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSave() }
            if (e.key === 'Escape') { setValue(message.content); setEditing(false) }
          }}
          className="min-h-[44px] resize-none bg-primary-foreground/10 text-primary-foreground placeholder:text-primary-foreground/50"
        />
        <div className="flex gap-1.5 justify-end text-xs">
          <button
            onClick={() => { setValue(message.content); setEditing(false) }}
            className="px-2 py-0.5 rounded hover:bg-primary-foreground/20"
          >
            取消
          </button>
          <button
            onClick={handleSave}
            className="px-2 py-0.5 rounded bg-primary-foreground/20 hover:bg-primary-foreground/30"
          >
            重发
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="group/content relative">
      <div className="whitespace-pre-wrap break-words">{message.content}</div>
      {/* 编辑按钮 */}
      {!isStreaming && (
        <button
          onClick={() => setEditing(true)}
          className="absolute -top-1 -right-1 hidden group-hover/content:flex items-center justify-center size-6 rounded bg-primary-foreground/20 text-primary-foreground hover:bg-primary-foreground/30"
          title="编辑并重发"
        >
          <Pencil className="size-3" />
        </button>
      )}
    </div>
  )
}

/** 内联工具调用列表 */
function InlineToolCalls({ toolCalls }: { toolCalls: WorkbenchMessage[] }) {
  return (
    <div className="mt-2 space-y-1">
      {toolCalls.map((tc) => (
        <InlineToolCall key={tc.id} tool={tc} />
      ))}
    </div>
  )
}

/** 单个内联工具调用（可折叠） */
function InlineToolCall({ tool }: { tool: WorkbenchMessage }) {
  const [expanded, setExpanded] = useState(false)
  const hasError = tool.metadata?.success === false

  return (
    <div className="rounded-md border border-border/50 bg-background/50 text-xs">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left hover:bg-accent/50 rounded-md transition-colors"
      >
        {hasError ? (
          <XCircle className="size-3 shrink-0 text-destructive" />
        ) : (
          <CheckCircle2 className="size-3 shrink-0 text-green-500" />
        )}
        <span className="font-medium">{tool.tool_name || '工具调用'}</span>
        <span className="flex-1" />
        {expanded ? (
          <ChevronDown className="size-3 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-3 shrink-0 text-muted-foreground" />
        )}
      </button>
      {expanded && (
        <div className="border-t border-border/50 px-2.5 py-2 space-y-2">
          {Object.keys(tool.tool_input).length > 0 && (
            <div>
              <div className="text-muted-foreground mb-1">输入</div>
              <pre className="whitespace-pre-wrap break-words bg-background/50 rounded p-1.5 text-[11px]">
                {JSON.stringify(tool.tool_input, null, 2)}
              </pre>
            </div>
          )}
          {Object.keys(tool.tool_output).length > 0 && (
            <div>
              <div className="text-muted-foreground mb-1">输出</div>
              <pre className="whitespace-pre-wrap break-words bg-background/50 rounded p-1.5 text-[11px]">
                {JSON.stringify(tool.tool_output, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/** 助手消息底部的元信息（token 用量、模型） */
function AssistantMeta({ message }: { message: WorkbenchMessage }) {
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

/** 助手消息 hover 操作按钮（复制 + 重新生成） */
function MessageActions({ message }: { message: WorkbenchMessage }) {
  const sendMessage = useWorkbenchStore((s) => s.sendMessage)
  const messages = useWorkbenchStore((s) => s.messages)
  const isStreaming = useWorkbenchStore((s) => s.isStreaming)

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content).then(() => {
      toast.success('已复制')
    })
  }

  const handleRegenerate = () => {
    if (isStreaming) return
    // 找到当前消息之前的最近一条 user 消息
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

/** 流式消息气泡 */
export function StreamingBubble({ message }: { message: StreamingMessage }) {
  return (
    <div className="flex gap-3 justify-start">
      <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10">
        <Bot className="size-4 text-primary animate-pulse" />
      </div>
      <div className="max-w-[80%] rounded-lg bg-muted px-4 py-2.5 text-sm space-y-2">
        {/* 活动指示器 */}
        {message.currentActivity && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="size-3 animate-spin" />
            <span>{message.currentActivity}</span>
          </div>
        )}

        {/* Agent Handoff 徽章 */}
        {message.handoffs.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {message.handoffs.map((h, i) => (
              <HandoffBadge key={i} from={h.from} to={h.to} />
            ))}
          </div>
        )}

        {/* 工具调用状态 */}
        {message.toolCalls.length > 0 && (
          <div className="space-y-1">
            {message.toolCalls.map((tc) => (
              <ToolCallIndicator key={tc.toolCallId} toolCall={tc} />
            ))}
          </div>
        )}

        {/* 错误信息（独立于正文） */}
        {message.error && (
          <div className="flex items-start gap-2 rounded-md bg-destructive/10 px-3 py-2 text-destructive text-xs">
            <AlertCircle className="size-3.5 shrink-0 mt-0.5" />
            <span>{message.error}</span>
          </div>
        )}

        {/* 文本内容 */}
        {message.content && (
          <MarkdownContent content={message.content} />
        )}

        {/* 流式光标 */}
        <span className="inline-block w-2 h-4 bg-primary/50 animate-pulse ml-0.5" />

        {/* 模型标签 */}
        {message.model && (
          <div className="text-[10px] text-muted-foreground">{message.model}</div>
        )}
      </div>
    </div>
  )
}

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

/** Markdown 内容渲染 */
function MarkdownContent({ content, isSystem }: { content: string; isSystem?: boolean }) {
  return (
    <div
      className={cn(
        'prose prose-sm dark:prose-invert max-w-none',
        'prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0',
        'prose-pre:my-2 prose-pre:rounded-md prose-pre:bg-background/80 prose-pre:p-3 prose-pre:text-xs',
        'prose-code:before:content-none prose-code:after:content-none',
        'prose-code:bg-background/80 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs',
        'prose-table:text-xs prose-th:px-2 prose-th:py-1 prose-td:px-2 prose-td:py-1',
        'prose-hr:my-2 prose-blockquote:my-1 prose-blockquote:border-l-2',
        isSystem && 'prose-red',
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {content}
      </ReactMarkdown>
    </div>
  )
}
