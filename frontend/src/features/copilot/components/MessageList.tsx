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

import { memo, useEffect, useRef, useState } from 'react'
import { Brain, Briefcase, Check, Copy, Loader2, MapPin, ThumbsDown, ThumbsUp, Wrench } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import remarkGfm from 'remark-gfm'

import { useAuth } from '@/features/auth'

import '../copilot.css'
import { bizHintParts, shortToolName } from '../domain'
import { useCopilot } from '../store'
import type { ChatMessage } from '../types'
import { ApprovalCard } from './ApprovalCard'
import { CopilotWelcome } from './CopilotWelcome'
import { RefQuoteCard, SelectionQuoteCard } from './RefQuote'
import { UserAvatar } from './UserAvatar'

// 三个气泡组件必须 memo：流式每个 delta 都 set({messages: s.messages.map(…)})
// 造出新数组 + 新消息对象，不 memo 的话每条历史气泡的 Markdown 树都要重算
// （200 条历史 × 几百个 delta）。props 只有 message 一个引用，未变的消息
// 走浅比较 bail out。
const ToolRow = memo(function ToolRow({ message }: { message: ChatMessage }) {
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
})

const ThinkingBlock = memo(function ThinkingBlock({ message }: { message: ChatMessage }) {
  const thinking = message.thinking ?? ''
  const thinkingNow = !message.thinkingDone
  // 思考结束自动收起：<details open> 是**静态属性**，只在挂载时生效——
  // 思考中以 open=true 挂载后，prop 变 false 也不会收起，于是正文开始后
  // 那片 396 字的思考内容继续占着 max-h-56，读起来就是一大块空白。
  // 改为受控：用 state 跟踪「用户是否手动改过」，没改过就跟随思考状态。
  const [userToggled, setUserToggled] = useState<boolean | null>(null)
  const open = userToggled ?? thinkingNow
  useEffect(() => {
    // 思考结束的那一刻清掉手动状态，回落到自动收起
    if (message.thinkingDone) setUserToggled((v) => (v === null ? v : null))
  }, [message.thinkingDone])
  if (!thinking) return null
  return (
    <details
      open={open}
      onToggle={(e) => setUserToggled(e.currentTarget.open)}
      className="mb-1.5 rounded-[10px] border border-dashed border-border bg-secondary/30 px-2.5 py-1.5"
    >
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[12px] text-muted-foreground">
        <Brain className="h-3 w-3 flex-none" />
        {/* 思考中用渐变流光（copilot-shimmer），结束后回落普通 muted 色 */}
        <span className={thinkingNow ? 'copilot-shimmer' : undefined}>
          {thinkingNow ? '深度思考中…' : `已深度思考（${thinking.length} 字）`}
        </span>
      </summary>
      <pre className="mt-1.5 max-h-56 overflow-y-auto border-t border-border pt-1.5 text-[11.5px] leading-relaxed break-words whitespace-pre-wrap text-muted-foreground">
        {thinking}
      </pre>
    </details>
  )
})

/** 点赞/点踩（P1-9b）：乐观更新在 store，失败自动回滚 */
function RateButtons({ messageId, rating }: { messageId: number; rating?: 'up' | 'down' }) {
  const rate = useCopilot((s) => s.rateMessage)
  const btn = (r: 'up' | 'down') => ({
    type: 'button' as const,
    'aria-label': r === 'up' ? '有帮助' : '没帮助',
    className:
      'flex h-6 w-6 items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary ' +
      (rating === r ? 'text-foreground' : 'opacity-60 hover:opacity-100'),
    onClick: () => void rate(messageId, rating === r ? 'none' : r),
  })
  return (
    <span className="ml-1.5 inline-flex gap-0.5 align-middle">
      <button {...btn('up')}>
        <ThumbsUp className="h-3 w-3" />
      </button>
      <button {...btn('down')}>
        <ThumbsDown className="h-3 w-3" />
      </button>
    </span>
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

const Bubble = memo(function Bubble({ message }: { message: ChatMessage }) {
  const user = useAuth((s) => s.user)
  if (message.role === 'tool') return <ToolRow message={message} />

  if (message.role === 'user') {
    const refs = message.refs ?? []
    const quote = message.quote
    const pageHint = message.pageHint
    const bizHint = message.bizHint
    const biz = bizHint ? bizHintParts(bizHint) : null
    // ml-auto：外层 flex-col 默认 stretch 会把这一行拉满整行，气泡于是贴左，
    // 右侧再空出 12%——观感就是「两边都空着一大块」。靠右是 IM 惯例，
    // 也让用户消息与左侧 AI 回答形成清晰的对位。
    return (
      <div className="ml-auto flex max-w-[88%] items-end gap-1.5">
        <div className="flex min-w-0 flex-1 flex-col items-end gap-1">
          {biz && bizHint && (
            <span
              className="flex max-w-full items-center gap-1 rounded-[6px] border border-border bg-card px-1.5 py-0.5 text-[11px] text-muted-foreground"
              title={`本条消息归属：${biz.unit}「${bizHint.title}」 ${biz.ref}（AI 据此直达对应案件/合同的数据）`}
            >
              <Briefcase className="h-3 w-3 flex-none text-foreground" />
              {/* 三段渲染而不是整串 truncate：id 是唯一的机器可读归属信息，
                  截断会把它吃掉。长标题只压中间段，尾部 #id 永不可隐藏 */}
              <span className="truncate">
                {biz.unit} · {biz.title}
              </span>
              <span className="flex-none tabular-nums text-foreground">{biz.ref}</span>
            </span>
          )}
          {pageHint && (
            <span
              className="flex max-w-full items-center gap-1 rounded-[6px] border border-border bg-card px-1.5 py-0.5 text-[11px] text-muted-foreground"
              title={`发送时所在页面：${pageHint}（AI 可据此了解页面内容）`}
            >
              <MapPin className="h-3 w-3 flex-none text-foreground" />
              <span className="max-w-52 truncate">{pageHint}</span>
            </span>
          )}
          {quote && (
            <div className="flex max-w-full flex-col items-end">
              <SelectionQuoteCard quote={quote} />
            </div>
          )}
          {refs.length > 0 && (
            <div className="flex max-w-full flex-col items-end">
              <RefQuoteCard refs={refs} />
            </div>
          )}
          {(message.content.trim() || (refs.length === 0 && !quote && !pageHint && !bizHint)) && (
            <div className="max-w-full rounded-[12px] rounded-br-[4px] bg-foreground px-3 py-2 text-[13px] leading-relaxed break-words whitespace-pre-wrap text-background">
              {message.content}
            </div>
          )}
        </div>
        <UserAvatar user={user} className="h-6 w-6" />
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
      {showCopy && (
        <span className="ml-1 inline-flex items-center align-middle">
          <RateButtons messageId={Number(message.id.slice(3))} rating={message.rating} />
          <CopyButton text={message.content} />
        </span>
      )}
    </div>
  )
})

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
  const noMoreHistory = useCopilot((s) => s.noMoreHistory)
  const loadingOlder = useCopilot((s) => s.loadingOlder)
  const loadOlderHistory = useCopilot((s) => s.loadOlderHistory)

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
      {/* 内容限宽居中：避免超宽屏一行长到难读，但同时别把面板里的可用宽度
          白白让出去。原先写死 max-w-3xl（768px）是按「全屏对话页」定的，可这里是
          **侧边栏面板**——面板拉到 1200px 时两侧各空 200px 以上，纯亏。
          改成 max-w-6xl（1152px）：默认 600 与常见拉宽（≤1150）
          都不产生留白，只有真拉到屏幕级才留白，且那时行宽也确实需要约束。
          empty 分支要撑满（h-full + flex）才能让欢迎页垂直居中：本层是
          CopilotWelcome 唯一的「高度来源」，不给高度它的 h-full 就塌成
          内容高、justify-center 无处可居（欢迎页贴顶、下面大片空白）。 */}
      <div
        className={
          empty
            ? 'mx-auto flex h-full w-full max-w-6xl flex-col'
            : 'mx-auto w-full max-w-6xl'
        }
      >
      {empty && <CopilotWelcome />}
      {loadingHistory && (
        <p className="py-6 text-center text-[12px] text-muted-foreground">正在加载历史…</p>
      )}
      {!loadingHistory && !noMoreHistory && messages.length >= 200 && (
        <div className="mb-2 flex justify-center">
          <button
            type="button"
            className="rounded-[8px] border border-border px-3 py-1 text-[12px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            onClick={() => void loadOlderHistory()}
            disabled={loadingOlder}
          >
            {loadingOlder ? '加载中…' : '加载更早的消息'}
          </button>
        </div>
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
    </div>
  )
}
