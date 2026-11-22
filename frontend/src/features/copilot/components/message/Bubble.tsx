/**
 * 单条消息的气泡：user / assistant / tool 三条分支。
 *
 * 从 `MessageList.tsx` 按职责拆出（后者已到软红线）。**纯搬运，行为零变化**。
 *
 * 两条必须原样保留的 DOM 契约：
 * - `data-msg-id`：滚动锚点（`hooks/use-scroll-anchor`）靠它定位「上次读到的那条」；
 * - `data-copilot-selection-root`：选区浮条（`SelectionBar` / `use-selection-quote`）
 *   的生效范围——user 气泡正文与 assistant 正文各一处，删掉就没有「选中即引用」。
 */

import { memo } from 'react'
import { Briefcase, MapPin } from 'lucide-react'

import { useAuth } from '@/features/auth'

import { bizHintParts, formatClock, ratableMessageId } from '../../domain'
// 直接从子模块引：canContinue / canRegenerate 属「这一轮能不能重放」的判据，
// 与转录渲染无关，不塞进 domain/index.ts 的出口表（那里是按域分块的）
import { canContinue, canRegenerate } from '../../domain'
import { useSmoothStreamText } from '../../hooks/use-smooth-stream-text'
import { useCopilot } from '../../store'
import type { ChatMessage } from '../../types'
import { AssistantMarkdown } from '../AssistantMarkdown'
import { MessageActions } from '../MessageActions'
import { SaveNoteButton } from '../SaveNoteButton'
import { RefQuoteCard, SelectionQuoteCard } from '../RefQuote'
import { StreamActivity } from '../StreamActivity'
import { OwnToolList } from '../ToolChips'
import { ToolRow } from '../ToolRow'
import { UserAvatar } from '../UserAvatar'
import { ThinkingBlock } from './ThinkingBlock'

export const Bubble = memo(function Bubble({
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
      <div data-msg-id={message.id} className="ml-auto flex max-w-[88%] items-end gap-1.5">
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
            // data-copilot-selection-root：用户气泡正文也允许「选中即引用」
            <div
              data-copilot-selection-root
              className="max-w-full rounded-[12px] rounded-br-[4px] bg-foreground px-3 py-2 text-[13px] leading-relaxed break-words whitespace-pre-wrap text-background"
            >
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
    <div data-msg-id={message.id} className="group relative max-w-full text-[13px] leading-relaxed text-foreground">
      <ThinkingBlock message={message} />
      {/* 「还在干活」要出现在**律师的注意力焦点**上（本栏气泡内、正文之前），
          而不是转录流里某一行工具条——后者他根本不会去看（见 StreamActivity） */}
      <StreamActivity message={message} />
      {content ? (
        // assistant 回答按 Markdown 渲染（gfm：表格/删除线/任务列表）；
        // react-markdown 默认不执行原始 HTML，无注入面；
        // rehype-highlight 只处理标注了语言的代码块（detect 关闭）
        // data-copilot-selection-root：选区浮条的生效范围（见 use-selection-quote）
        <div data-copilot-selection-root className="copilot-md break-words pr-0">
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
        <>
          <MessageActions
            content={message.content}
            messageId={ratableMessageId(message)}
            rating={message.rating}
            createdAt={message.createdAt}
            // 判据在 domain/turn-actions.ts：必须已落库、必须是 assistant；
            // 续写还要求这条被截断过（否则"接哪一段"没有对象）
            regenerable={canRegenerate(message)}
            continuable={canContinue(message)}
            onRegenerate={(mode) => {
              const id = ratableMessageId(message)
              if (id !== null) void useCopilot.getState().regenerate(id, mode)
            }}
          />
          {/* 存进项目笔记：把这条回答里的结论落到项目上，同团队可见。
              只在这里出现（不在流式气泡上）：还没落库的会话没有 sessionId，
              存了也无处归属。 */}
          <SaveNoteButton content={message.content} />
        </>
      )}
    </div>
  )
})
