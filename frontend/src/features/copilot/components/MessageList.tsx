/**
 * 转录列表：气泡 + 工具行 + 审批卡 + 错误行。
 * 自动吸底滚动用 ref 直改 DOM（高频 delta 时不经 React 协调），
 * 用户上翻查看历史时停止吸底，回到底部附近再恢复。
 */

import { useEffect, useRef } from 'react'
import { Brain, Wrench } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
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

function Bubble({ message }: { message: ChatMessage }) {
  if (message.role === 'tool') return <ToolRow message={message} />

  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-[12px] rounded-br-[4px] bg-foreground px-3 py-2 text-[13px] leading-relaxed break-words whitespace-pre-wrap text-background">
          {message.content}
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-full text-[13px] leading-relaxed text-foreground">
      <ThinkingBlock message={message} />
      {message.content ? (
        // assistant 回答按 Markdown 渲染（gfm：表格/删除线/任务列表）；
        // react-markdown 默认不执行原始 HTML，无注入面
        <div className="copilot-md break-words">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
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
    </div>
  )
}

export function MessageList() {
  const messages = useCopilot((s) => s.messages)
  const approvals = useCopilot((s) => s.approvals)
  const streaming = useCopilot((s) => s.streaming)
  const loadingHistory = useCopilot((s) => s.loadingHistory)
  const lastError = useCopilot((s) => s.lastError)

  const scrollRef = useRef<HTMLDivElement>(null)
  const stickToBottom = useRef(true)

  const handleScroll = () => {
    const el = scrollRef.current
    if (el) stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60
  }

  useEffect(() => {
    const el = scrollRef.current
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight
  }, [messages, approvals, lastError])

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
