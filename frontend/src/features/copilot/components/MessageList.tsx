/**
 * 转录列表：气泡 + 工具行 + 审批卡 + 排队提示 + 错误行。
 * 自动吸底滚动用 ref 直改 DOM（高频 delta 时不经 React 协调），
 * 用户上翻查看历史时停止吸底，回到底部附近再恢复。
 *
 * - 排队提示：池满时后端发 activity{queued,position}，store 记 queuePosition，
 *   首个推进事件（delta 等）自动清除——用户不用盯着转圈猜发生了什么
 * - assistant 气泡：Markdown（GFM）渲染 + 代码块语法高亮（rehype-highlight，
 *   未标注语言的块不高亮）；hover 显示复制按钮（复制 Markdown 源码）
 */

import { useEffect, useRef, useState } from 'react'
import { Brain, Check, Copy, FolderOpen, Loader2, MapPin, Wrench } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import remarkGfm from 'remark-gfm'

import '../copilot.css'
import { shortToolName } from '../domain'
import { useCopilot } from '../store'
import type { ChatMessage } from '../types'
import { ApprovalCard } from './ApprovalCard'

function ToolRow({ message }: { message: ChatMessage }) {
  const name = shortToolName(message.toolName)
  return (
    <details className="group rounded-[10px] border border-border bg-secondary/40 px-2.5 py-1.5">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[12px] text-muted-foreground">
        <Wrench className="h-3 w-3 flex-none" />
        <span className="truncate">
          {message.content ? '已完成' : '调用中'} · {name}
        </span>
      </summary>
      {message.content && (
        <pre className="mt-1.5 max-h-56 overflow-y-auto border-t border-border pt-1.5 font-mono text-[11px] leading-relaxed break-all whitespace-pre-wrap text-secondary-foreground">
          {message.content}
        </pre>
      )}
    </details>
  )
}

function ThinkingBlock({ message }: { message: ChatMessage }) {
  const thinking = message.thinking ?? ''
  if (!thinking) return null
  // 思考中自动展开（让用户看到实时推理），思考结束（正文已开始）自动收起，
  // 但保留手动展开能力。用 details + open 受控会打断用户手动操作，
  // 所以只用 defaultOpen 决定初始态。
  const thinkingNow = !message.thinkingDone
  return (
    <details
      open={thinkingNow}
      className="mb-1.5 rounded-[10px] border border-dashed border-border bg-secondary/30 px-2.5 py-1.5"
    >
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[12px] text-muted-foreground">
        <Brain className="h-3 w-3 flex-none" />
        <span>{thinkingNow ? '深度思考中…' : `已深度思考（${thinking.length} 字）`}</span>
      </summary>
      <pre className="mt-1.5 max-h-56 overflow-y-auto border-t border-border pt-1.5 text-[11.5px] leading-relaxed break-words whitespace-pre-wrap text-muted-foreground">
        {thinking}
      </pre>
    </details>
  )
}

/** 复制助手回答的 Markdown 源码（hover 浮现；无剪贴板环境静默忽略） */
function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!copied) return
    const timer = setTimeout(() => setCopied(false), 1500)
    return () => clearTimeout(timer)
  }, [copied])
  return (
    <button
      type="button"
      className="absolute top-0 right-0 flex h-6 w-6 items-center justify-center rounded-[6px] bg-card text-muted-foreground opacity-0 shadow-sm transition-opacity group-hover:opacity-100 focus-visible:opacity-100 hover:text-foreground"
      aria-label="复制回答"
      title="复制 Markdown 源码"
      onClick={() => {
        navigator.clipboard
          ?.writeText(text)
          .then(() => setCopied(true))
          .catch(() => {})
      }}
    >
      {copied ? <Check className="h-3 w-3 text-emerald-600" /> : <Copy className="h-3 w-3" />}
    </button>
  )
}

function Bubble({ message }: { message: ChatMessage }) {
  if (message.role === 'tool') return <ToolRow message={message} />

  if (message.role === 'user') {
    const refs = message.refs ?? []
    const pageHint = message.pageHint
    return (
      <div className="flex max-w-[85%] flex-col items-end gap-1">
        {pageHint && (
          <span
            className="flex max-w-full items-center gap-1 rounded-[6px] border border-border bg-card px-1.5 py-0.5 text-[11px] text-muted-foreground"
            title={`发送时所在页面：${pageHint}（AI 可据此了解页面内容）`}
          >
            <MapPin className="h-3 w-3 flex-none text-primary" />
            <span className="max-w-52 truncate">{pageHint}</span>
          </span>
        )}
        {refs.length > 0 && (
          <div className="flex max-w-full flex-wrap justify-end gap-1">
            {refs.map((ref) => (
              <span
                key={`${ref.contractId}-${ref.subpath}`}
                className="flex max-w-full items-center gap-1 rounded-[6px] border border-border bg-card px-1.5 py-0.5 text-[11px] text-muted-foreground"
                title={`合同 ${ref.contractId} · ${ref.subpath}（引用原文件）`}
              >
                <FolderOpen className="h-3 w-3 flex-none text-primary" />
                <span className="max-w-52 truncate">{ref.subpath}</span>
              </span>
            ))}
          </div>
        )}
        {(message.content.trim() || (refs.length === 0 && !pageHint)) && (
          <div className="max-w-full rounded-[12px] rounded-br-[4px] bg-foreground px-3 py-2 text-[13px] leading-relaxed break-words whitespace-pre-wrap text-background">
            {message.content}
          </div>
        )}
      </div>
    )
  }

  const showCopy = !message.streaming && Boolean(message.content)
  return (
    <div className="group relative max-w-full text-[13px] leading-relaxed text-foreground">
      <ThinkingBlock message={message} />
      {message.content ? (
        // assistant 回答按 Markdown 渲染（gfm：表格/删除线/任务列表）；
        // react-markdown 默认不执行原始 HTML，无注入面；
        // rehype-highlight 只处理标注了语言的代码块（detect 关闭）
        <div className="copilot-md break-words pr-0">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeHighlight]}
            components={{
              a: (props) => <a {...props} target="_blank" rel="noreferrer" />,
            }}
          >
            {message.content}
          </ReactMarkdown>
        </div>
      ) : message.streaming ? null : message.thinking ? null : (
        '（无内容）'
      )}
      {message.streaming && <span className="ml-0.5 inline-block animate-pulse text-primary">▍</span>}
      {message.truncated && (
        <span className="ml-1.5 rounded-[4px] border border-border px-1 py-px text-[10.5px] text-muted-foreground">已中断</span>
      )}
      {showCopy && <CopyButton text={message.content} />}
    </div>
  )
}

/** 排队提示条：池满时显示名次（position 含自己，「前方 N 人」= N-1） */
function QueueBanner({ position }: { position: number }) {
  const ahead = Math.max(0, position - 1)
  return (
    <div className="mb-2 flex items-center gap-1.5 rounded-[8px] border border-border bg-secondary/40 px-2.5 py-1.5 text-[12px] text-muted-foreground">
      <Loader2 className="h-3 w-3 flex-none animate-spin" />
      {ahead > 0 ? (
        <span>
          当前使用人数较多，排队中 · 前方 {ahead} 人…
        </span>
      ) : (
        <span>排队中，即将开始…</span>
      )}
    </div>
  )
}

export function MessageList() {
  const messages = useCopilot((s) => s.messages)
  const approvals = useCopilot((s) => s.approvals)
  const streaming = useCopilot((s) => s.streaming)
  const loadingHistory = useCopilot((s) => s.loadingHistory)
  const lastError = useCopilot((s) => s.lastError)
  const queuePosition = useCopilot((s) => s.queuePosition)

  const scrollRef = useRef<HTMLDivElement>(null)
  const stickToBottom = useRef(true)

  const handleScroll = () => {
    const el = scrollRef.current
    if (el) stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60
  }

  useEffect(() => {
    const el = scrollRef.current
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight
  }, [messages, approvals, lastError, queuePosition])

  const empty = messages.length === 0 && !streaming && !loadingHistory

  return (
    <div ref={scrollRef} onScroll={handleScroll} className="copilot-messages flex-1 overflow-y-auto px-3.5 py-3">
      {empty && (
        <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
          <p className="text-[13px] font-medium text-foreground">问点什么，或让它查系统数据</p>
          <p className="text-[12px] leading-relaxed text-muted-foreground">
            例如：列一下我名下的案件、看看合同 386 的归档状态。
            <br />
            AI 回答仅供参考，法律判断需由律师复核。
          </p>
        </div>
      )}
      {loadingHistory && (
        <p className="py-6 text-center text-[12px] text-muted-foreground">正在加载历史…</p>
      )}
      {queuePosition !== null && <QueueBanner position={queuePosition} />}
      <div className="flex flex-col gap-2.5">
        {messages.map((m) => (
          <Bubble key={m.id} message={m} />
        ))}
      </div>
      {approvals.length > 0 && (
        <div className="mt-2.5 flex flex-col gap-2">
          {approvals.map((a) => (
            <ApprovalCard key={a.approvalId} approval={a} />
          ))}
        </div>
      )}
      {lastError && <p className="mt-2 text-[12px] text-destructive">{lastError}</p>}
    </div>
  )
}
