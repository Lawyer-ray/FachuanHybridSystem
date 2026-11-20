/**
 * 转录列表的**装配骨架**：订阅 store、分组、吸底滚动、锚点接线、骨架布局。
 *
 * 单条消息的三种气泡在 `message/Bubble.tsx`（+ `message/ThinkingBlock.tsx`），
 * 列表外壳控件（排队条 / 加载更早 / 回到底部）在 `message/ListChrome.tsx`。
 * 本文件只留「一个列表」这件事本身的逻辑，改气泡外观请去 message/ 下。
 *
 * 自动吸底滚动用 ref 直改 DOM（高频 delta 时不经 React 协调），
 * 用户上翻查看历史时停止吸底，回到底部附近再恢复。
 *
 * - 排队提示：池满时后端发 activity{queued,position}，store 记 queuePosition，
 *   首个推进事件（delta 等）自动清除——用户不用盯着转圈猜发生了什么
 * - 消息级操作（复制/评分/时间戳）收在 MessageActions；正文里选中一段会浮出
 *   SelectionBarLayer（引用到输入框），两者的取舍见各自文件头
 * - 多答轮次：相邻的 2~4 条 assistant 交给 AnswerGroupView/MultiAnswers 并排
 *   （单条走普通气泡，与引入该功能前完全一致）
 * - 滚动位置按会话记「语义锚点」（见 hooks/use-scroll-anchor）：切走前存、
 *   历史就位后落回，别让律师翻到一半被丢回顶部
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { LoadingBlock } from '@/components/shared/AsyncState'

import '../copilot.css'
import { groupAnswerRuns } from '../domain'
import { useScrollAnchor } from '../hooks/use-scroll-anchor'
import { useCopilot } from '../store'
import type { ChatMessage } from '../types'
import { AnswerGroupView } from './AnswerGroupView'
import { ApprovalCard } from './ApprovalCard'
import { CopilotWelcome } from './CopilotWelcome'
import { ErrorNotice } from './ErrorNotice'
import { LoadOlderButton, QueueBanner, ScrollToBottomButton } from './message/ListChrome'
import { Bubble } from './message/Bubble'
import { QuestionCard } from './questions/QuestionCard'
import { SelectionBarLayer } from './SelectionBar'

/** 分页按钮的显示门槛：历史一次性拉 200 条，到了这个数才可能还有更早的 */
const OLDER_HISTORY_THRESHOLD = 200

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
  const sessionId = useCopilot((s) => s.sessionId)

  const scrollRef = useRef<HTMLDivElement>(null)
  const stickToBottom = useRef(true)
  // 与 stickToBottom 同步的**可见**状态：只有它变了才需要重渲染（渲染「回到底部」钮）
  const [atBottom, setAtBottom] = useState(true)
  // 每会话的滚动位置（语义锚点，见 hooks/use-scroll-anchor）：切走前记、回来时落回
  const anchorApi = useScrollAnchor(scrollRef)
  // 写 ref 只能在 effect 里（渲染期写会被 React Compiler 判错），而恢复要在
  // 「历史已就位」之后跑一次——两个 effect 各自合法，串起来就是「拿到最新函数再调」。
  const anchorApiRef = useRef(anchorApi)
  useEffect(() => {
    anchorApiRef.current = anchorApi
  })

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 60
    stickToBottom.current = near
    setAtBottom((prev) => (prev === near ? prev : near))
    // 记位置必须在滚动事件里：`useEffect` 的 cleanup 跑在 DOM 已换成新会话之后，
    // 那时量到的是空转录，锚点白丢（见 use-scroll-anchor 的接线说明）。
    anchorApiRef.current.saveAnchor(sessionId)
  }

  // 分组与行渲染都固定引用：`AnswerGroupView`/`MultiAnswers` 都是 memo 的，
  // 每次渲染新建的箭头函数会把它们一起击穿（流式期间每个 delta 都重算一轮）。
  const groups = useMemo(() => groupAnswerRuns(messages), [messages])
  const renderAnswer = useCallback(
    (answer: ChatMessage, hideTools: ReadonlySet<string>) => (
      <Bubble message={answer} hideTools={hideTools} />
    ),
    [],
  )

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

  // 历史就位后把位置落回这个会话上次读到的行。只在**不在 follow 状态**时做：
  // 律师正贴着底看实时输出时把视图拽回历史位置，比丢位置更糟。
  useEffect(() => {
    if (loadingHistory || streaming) return
    anchorApiRef.current.restoreAnchor(sessionId)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 只在「会话换了 / 历史刚就位」时落一次
  }, [sessionId, loadingHistory])

  const empty = messages.length === 0 && !streaming && !loadingHistory

  return (
    // data-copilot-scroll：选区浮条要靠它算可见框（见 SelectionBar.visibleBoundsOf）
    <div ref={scrollRef} onScroll={handleScroll} data-copilot-scroll className="copilot-messages flex-1 overflow-y-auto px-3.5 py-3">
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
        {!loadingHistory && !noMoreHistory && messages.length >= OLDER_HISTORY_THRESHOLD && (
          <LoadOlderButton loading={loadingOlder} onLoad={loadOlderHistory} />
        )}
        {queuePosition !== null && <QueueBanner position={queuePosition} />}
        <div className="flex flex-col gap-2.5">
          {groups.map((group) => (
            <AnswerGroupView
              key={group.answers[0]!.id}
              answers={group.answers}
              // hideTools：多栏里已归位到各栏的工具行，不再当转录流独立项渲染
              // （否则未完成的工具会同时出现在气泡内活动行和外面的工具行里）
              renderAnswer={renderAnswer}
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
        <ErrorNotice />
      </div>
      {/* 选中即引用的浮条（position: fixed，挂哪里都行；放在这里才能跟着列表的生命周期） */}
      <SelectionBarLayer />
      {messages.length > 0 && !atBottom && <ScrollToBottomButton onClick={scrollToBottom} />}
    </div>
  )
}
