/**
 * 转录列表：气泡 + 工具行 + 审批卡 + 排队提示 + 错误行。
 * 自动吸底滚动用 ref 直改 DOM（高频 delta 时不经 React 协调），
 * 用户上翻查看历史时停止吸底，回到底部附近再恢复。
 *
 * - 排队提示：池满时后端发 activity{queued,position}，store 记 queuePosition，
 *   首个推进事件（delta 等）自动清除——用户不用盯着转圈猜发生了什么
 * - assistant 气泡：Markdown（GFM）渲染 + 代码块语法高亮（rehype-highlight，
 *   未标注语言的块不高亮）；hover 显示复制按钮（复制 Markdown 源码）
 * - 等待期观感：正文未到但工具在跑时，气泡内显示「正在查 XX…」呼吸行
 *   （见 StreamActivity）——否则先调工具的 dsh / openai-agents 看起来像卡死
 * - 多答轮次：相邻的 2~4 条 assistant 交给 MultiAnswers 并排（单条走普通气泡，
 *   与引入该功能前完全一致）
 */

import { memo, useEffect, useRef, useState } from 'react'
import { Brain, Briefcase, Check, Copy, Loader2, MapPin, ThumbsDown, ThumbsUp } from 'lucide-react'

import { useAuth } from '@/features/auth'
import { LoadingBlock } from '@/components/shared/AsyncState'
import { useCopyFeedback } from '@/hooks/use-copy-feedback'

import '../copilot.css'
import { bizHintParts, formatClock, groupAnswerRuns, ratableMessageId } from '../domain'
import { useSmoothStreamText } from '../hooks/use-smooth-stream-text'
import { useCopilot } from '../store'
import type { ChatMessage } from '../types'
import { ApprovalCard } from './ApprovalCard'
import { QuestionCard } from './questions/QuestionCard'
import { AssistantMarkdown } from './AssistantMarkdown'
import { AnswerGroupView } from './AnswerGroupView'
import { CopilotWelcome } from './CopilotWelcome'
import { RefQuoteCard, SelectionQuoteCard } from './RefQuote'
import { StreamActivity } from './StreamActivity'
import { OwnToolList } from './ToolChips'
import { ToolRow } from './ToolRow'
import { UserAvatar } from './UserAvatar'

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

/**
 * 点赞/点踩（P1-9b）：乐观更新在 store，失败自动回滚。
 *
 * `messageId` 为 null = 本条还没落库（实时气泡）：按钮置灰并说明原因。
 * 旧写法直接 `Number(message.id.slice(3))`，对 `local-3` 得到 NaN——按钮看起来
 * 可点，点了必然失败且没有任何反馈（见 domain/message-id.ts）。
 */
function RateButtons({ messageId, rating }: { messageId: number | null; rating?: 'up' | 'down' }) {
  const rate = useCopilot((s) => s.rateMessage)
  const disabled = messageId === null
  const btn = (r: 'up' | 'down') => ({
    type: 'button' as const,
    'aria-label': r === 'up' ? '有帮助' : '没帮助',
    disabled,
    title: disabled ? '本条尚未落库，暂不可评分' : r === 'up' ? '有帮助' : '没帮助',
    className:
      'flex h-6 w-6 items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-40 ' +
      (rating === r ? 'text-foreground' : 'opacity-60 hover:opacity-100'),
    onClick: () => {
      if (messageId === null) return
      void rate(messageId, rating === r ? 'none' : r)
    },
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

/** 复制助手回答的 Markdown 源码（hover 浮现） */
function CopyButton({ text }: { text: string }) {
  // 必须走 useCopyFeedback：内网 http 部署下 navigator.clipboard 不存在，
  // 手写调用只会静默失败（点了没任何反馈），它内部带 execCommand 兜底。
  const { copied, copy } = useCopyFeedback({ resetMs: 1500 })
  return (
    <button
      type="button"
      className="absolute top-0 right-0 flex h-6 w-6 items-center justify-center rounded-[6px] bg-card text-muted-foreground opacity-0 shadow-sm transition-opacity group-hover:opacity-100 focus-visible:opacity-100 hover:text-foreground"
      aria-label="复制回答"
      title="复制 Markdown 源码"
      onClick={() => void copy(text)}
    >
      {copied ? <Check className="h-3 w-3 text-emerald-600" /> : <Copy className="h-3 w-3" />}
    </button>
  )
}

const Bubble = memo(function Bubble({
  message,
  hideTools,
}: {
  message: ChatMessage
  /** 已归位到各栏的工具行 id：命中的 tool 消息不在这里渲染（见 AnswerGroupView） */
  hideTools?: ReadonlySet<string>
}) {
  const user = useAuth((s) => s.user)
  // 流式平滑放字：只对正在直播的 assistant 消息生效，历史消息与非直播原样返回。
  // 见 docs/harness/pitfalls.md PIT-007 —— 直接渲染原始 delta 会「一顿一顿」，
  // 且每来一个字就重解析整篇 markdown（成本随回复长度线性涨，长回复掉帧）。
  //
  // **必须放在所有 early return 之前**：hook 调用顺序不能依赖 message.role，
  // 否则同一位置在 role 切换（tool → assistant）时会改变 hook 数量，React 直接报错。
  // 非 assistant 消息传 live=false，hook 内部直接返回 full，不调度任何动画帧。
  const smoothContent = useSmoothStreamText(
    message.content,
    message.role === 'assistant' && message.streaming === true,
  )

  if (message.role === 'tool') {
    // 工具已经在气泡内（活动行）或气泡下（chip）显示了，外面不再来一条
    if (hideTools?.has(message.id)) return null
    return <ToolRow message={message} />
  }

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
          {message.createdAt ? (
            <time
              className="text-[10.5px] text-muted-foreground tabular-nums"
              dateTime={new Date(message.createdAt).toISOString()}
              title={new Date(message.createdAt).toLocaleString('zh-CN')}
            >
              {formatClock(message.createdAt)}
            </time>
          ) : null}
        </div>
        <UserAvatar user={user} className="h-6 w-6" />
      </div>
    )
  }

  const content = smoothContent

  // 多答里没跑成的那一栏：明写「本轮未做」而不是留空。留空的话界面上只有一个
  // 栏头，看起来像「回答了但内容丢了」——律师会去查是不是系统坏了。
  if (message.failed && !message.content && !message.streaming) {
    return (
      <div className="text-[12px] leading-relaxed text-muted-foreground" data-testid="answer-failed">
        本轮未做
      </div>
    )
  }

  const showCopy = !message.streaming && Boolean(message.content)
  return (
    <div className="group relative max-w-full text-[13px] leading-relaxed text-foreground">
      <ThinkingBlock message={message} />
      {/* 「还在干活」要出现在**律师的注意力焦点**上（本栏气泡内、正文之前），
          而不是转录流里某一行工具条——后者他根本不会去看（见 StreamActivity） */}
      <StreamActivity message={message} />
      {content ? (
        // assistant 回答按 Markdown 渲染（gfm：表格/删除线/任务列表）；
        // react-markdown 默认不执行原始 HTML，无注入面；
        // rehype-highlight 只处理标注了语言的代码块（detect 关闭）
        <div className="copilot-md break-words pr-0">
          <AssistantMarkdown text={content} streaming={message.streaming === true} />
        </div>
      ) : message.streaming ? null : message.thinking ? null : (
        '（无内容）'
      )}
      {message.streaming && <span className="ml-0.5 inline-block animate-pulse text-primary">▍</span>}
      {/* 这个 agent 自己调过的工具：挂在他自己的话下面，而不是所有 agent 的
          工具混成一个列表堆在底部（真实反馈：一坨分不清谁的工具条、还占满整行）。
          只在多栏模式由 mergeAgentAnswers 填充；单栏时 tools 为空，工具行仍按
          原时间顺序平铺（那条路径的顺序本身就是对的）。 */}
      {message.tools && message.tools.length > 0 && <OwnToolList tools={message.tools} />}
      {message.truncated && (
        <span className="ml-1.5 rounded-[4px] border border-border px-1 py-px text-[10.5px] text-muted-foreground">已中断</span>
      )}
      {showCopy && (
        <span className="ml-1 inline-flex items-center align-middle">
          <RateButtons messageId={ratableMessageId(message)} rating={message.rating} />
          <CopyButton text={message.content} />
          {message.createdAt ? (
            <time
              className="ml-1 text-[10.5px] text-muted-foreground tabular-nums"
              dateTime={new Date(message.createdAt).toISOString()}
              title={new Date(message.createdAt).toLocaleString('zh-CN')}
            >
              {formatClock(message.createdAt)}
            </time>
          ) : null}
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

export function MessageList({ wide = false }: { wide?: boolean } = {}) {
  const messages = useCopilot((s) => s.messages)
  const approvals = useCopilot((s) => s.approvals)
  const pendingQuestions = useCopilot((s) => s.pendingQuestions)
  const streaming = useCopilot((s) => s.streaming)
  const loadingHistory = useCopilot((s) => s.loadingHistory)
  const lastError = useCopilot((s) => s.lastError)
  const queuePosition = useCopilot((s) => s.queuePosition)
  const noMoreHistory = useCopilot((s) => s.noMoreHistory)
  const loadingOlder = useCopilot((s) => s.loadingOlder)
  const loadOlderHistory = useCopilot((s) => s.loadOlderHistory)

  const scrollRef = useRef<HTMLDivElement>(null)
  const stickToBottom = useRef(true)
  // 与 stickToBottom 同步的**可见**状态：只有它变了才需要重渲染（渲染「回到底部」钮）
  const [atBottom, setAtBottom] = useState(true)

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 60
    stickToBottom.current = near
    setAtBottom((prev) => (prev === near ? prev : near))
  }

  const scrollToBottom = () => {
    const el = scrollRef.current
    stickToBottom.current = true
    setAtBottom(true)
    if (el) el.scrollTop = el.scrollHeight
  }

  useEffect(() => {
    const el = scrollRef.current
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight
  }, [messages, approvals, pendingQuestions, lastError, queuePosition])

  const empty = messages.length === 0 && !streaming && !loadingHistory

  return (
    <div ref={scrollRef} onScroll={handleScroll} className="copilot-messages flex-1 overflow-y-auto px-3.5 py-3">
      {/* 内容限宽居中：避免超宽屏一行长到难读，但同时别把面板里的可用宽度
          白白让出去。原先写死 max-w-3xl（768px）是按「全屏对话页」定的，可这里是
          **侧边栏面板**——面板拉到 1200px 时两侧各空 200px 以上，纯亏。
          改成 max-w-6xl（1152px）：默认 600 与常见拉宽（≤1150）
          都不产生留白，只有真拉到屏幕级才留白，且那时行宽也确实需要约束。

          ``wide`` 为 true 时**解除**这个上限：独立助手页（``/assistant``）整屏
          都是对话区，多 agent 并排时每栏要尽量宽才读得下。默认 false，抽屉面板
          的行为逐字不变——这是刻意的：抽屉在 1200px 宽的屏幕里拉到 1152 已经
          贴边，再放开只会让单栏正文行长到难读。
          empty 分支要撑满（h-full + flex）才能让欢迎页垂直居中：本层是
          CopilotWelcome 唯一的「高度来源」，不给高度它的 h-full 就塌成
          内容高、justify-center 无处可居（欢迎页贴顶、下面大片空白）。 */}
      <div
        className={
          empty
            ? `mx-auto flex h-full w-full flex-col ${wide ? '' : 'max-w-6xl'}`
            : `mx-auto w-full ${wide ? '' : 'max-w-6xl'}`
        }
      >
      {empty && <CopilotWelcome />}
      {loadingHistory && <LoadingBlock text="正在加载历史…" className="py-6" />}
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
        {groupAnswerRuns(messages).map((group) => (
          <AnswerGroupView
            key={group.answers[0]!.id}
            answers={group.answers}
            // hideTools：多栏里已归位到各栏的工具行，不再当转录流独立项渲染
            // （否则未完成的工具会同时出现在气泡内活动行和外面的工具行里）
            renderAnswer={(answer, hideTools) => <Bubble message={answer} hideTools={hideTools} />}
          />
        ))}
      </div>
      {approvals.length > 0 && (
        <div className="mt-2.5 flex flex-col gap-2">
          {approvals.map((a) => (
            <ApprovalCard key={a.approvalId} approval={a} />
          ))}
        </div>
      )}
      {pendingQuestions.length > 0 && (
        <div className="mt-2.5 flex flex-col gap-2">
          {pendingQuestions.map((q) => (
            <QuestionCard key={q.questionId} question={q} />
          ))}
        </div>
      )}
      {lastError && <p className="mt-2 text-[12px] text-destructive">{lastError}</p>}
      </div>
      {/* 上翻看历史后一键回到最新：长回答（几十屏）里上翻后只能一直滚回去。
          sticky bottom-0 让它只在本容器视野内吸底，不跟随页面其他区域。 */}
      {messages.length > 0 && !atBottom && (
        <div className="pointer-events-none sticky bottom-0 z-10 mt-2 flex justify-end">
          <button
            type="button"
            className="pointer-events-auto rounded-full border border-border bg-card px-2.5 py-1 text-[11.5px] text-muted-foreground shadow-sm transition-colors hover:text-foreground"
            title="跳到最新一条"
            onClick={scrollToBottom}
          >
            回到底部 ↓
          </button>
        </div>
      )}
    </div>
  )
}
