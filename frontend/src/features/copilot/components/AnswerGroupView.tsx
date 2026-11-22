/**
 * 一轮回答的渲染决策：单栏（1 条）走普通气泡，多栏（2~4 条）交给 MultiAnswers
 * 并排。
 *
 * ## 单栏：连续的 tool 消息收成 chip 带
 *
 * 一条工具占一整行时，16 条工具吃掉约 450px，而每条的信息只有「工具名 + 耗时」。
 * 所以单栏按顺序扫一遍 `answers`，把**连续**的 tool 消息聚成一段交给 `ToolChipList`
 * （一行放多枚、自动换行；点开的那枚 `open:basis-full` 独占整行看返回值），非 tool
 * 消息照旧一条一条走 `renderAnswer`。**消息顺序不变**：聚段只换排版，不重排、不跨
 * 消息合并（换行容器内部的先后就是到达先后）。
 *
 * 从 MessageList 拆出（后者已到软红线）：这里同时承担三件互相关联的事——
 * 「这一轮跑了几家」的还原、同栏多段消息的合并、以及单栏/多栏的分派。它们
 * 共用一个判据，分开放两处迟早漂移（一处合并了、另一处没合并，同一轮会时
 * 而两栏时而不合并）。
 *
 * **性能约定（改之前先读）**：流式期间每个 delta 都会让 MessageList 重渲染，
 * 本组件因此在热路径上。所以
 * - 组件本身 `memo`，只在 `answers` 或 `renderAnswer` 引用变化时重算；
 * - 合并（mergeAgentAnswers / attachedToolIds）走 `useMemo`，不随每次渲染重跑；
 * - 传给 `MultiAnswers` 的回调用 `useCallback` 固定引用——它内部是 `memo`，
 *   每次新建一个箭头函数就等于把 memo 关掉了（这正是改造前的问题）。
 */

import { Fragment, memo, useCallback, useMemo } from 'react'

import { attachedToolIds, DEFAULT_AGENT_KIND, distinctAgentKinds, HISTORY_PAGE_SIZE, mergeAgentAnswers } from '../domain'
// 从子模块直引：`domain/index.ts` 的桶出口不在本片白名单内（与 LaneFactsBadge 同一口径）
import { reviewTurnOf } from '../domain'
import { useCopilot } from '../store'
import type { ChatMessage } from '../types'
import { MultiAnswers } from './MultiAnswers'
import { ToolChipList } from './ToolChips'

/** 单栏不涉及「工具归位」（工具收进 chip 带），共用一个空集避免每次新建 */
const EMPTY_HIDE_TOOLS: ReadonlySet<string> = new Set()

/** 单栏的一段：一串**连续的** tool 消息（收进 chip 带），或一条普通消息 */
type AnswerRun = { key: string; tools: ChatMessage[] } | { key: string; message: ChatMessage }

/** 按原顺序聚段：连续的 tool 消息并为一段，其余消息各自一段 */
function groupToolRuns(answers: ChatMessage[]): AnswerRun[] {
  const runs: AnswerRun[] = []
  for (const message of answers) {
    if (message.role !== 'tool') {
      runs.push({ key: message.id, message })
      continue
    }
    const last = runs[runs.length - 1]
    if (last && 'tools' in last) last.tools.push(message)
    else runs.push({ key: message.id, tools: [message] })
  }
  return runs
}

export const AnswerGroupView = memo(function AnswerGroupView({
  answers,
  renderAnswer,
}: {
  answers: ChatMessage[]
  /**
   * 复用 MessageList 的 Bubble（Markdown / 平滑放字 / 复制按钮全套都在它里面）。
   *
   * `hideTools`：这一轮里已归位到各栏的工具行 id。多栏时工具行不能作为转录流
   * 独立项再渲染一遍（正文未到时它由本栏气泡内的活动行显示、到了之后由本栏下方
   * 的 chip 显示），但**同一条工具在别的轮次里仍要照旧平铺**——所以按 id 排除，
   * 不能简单地对多栏轮次一律不渲染工具。
   *
   * **必须是稳定引用**（调用方用 useCallback），否则下面的 memo 全部失效。
   */
  renderAnswer: (message: ChatMessage, hideTools: ReadonlySet<string>) => React.ReactNode
}) {
  // 栏头高亮的是「当前默认后端」：与后端清单第一项同口径（新建会话默认用它），
  // 律师据此知道哪一栏是自己平时问的那个。
  const defaultAgentKind = useCopilot((s) => s.selectedAgentKind || DEFAULT_AGENT_KIND)
  // 栏头要标「这一栏没有审批闸门」：清单引用稳定（store 切片），不会击穿 memo
  const backends = useCopilot((s) => s.backends)

  // 裁决卡的数据源：后端 `turn` = 会话里第几条 user 消息。
  //
  // `windowComplete` 是必须的诚实边界：历史按 HISTORY_PAGE_SIZE 分页，>200 条的
  // 老会话加载的是「最新一页」，从窗口里数 user 消息会少数几轮——那样会把 A 轮
  // 的评审挂到 B 轮的答案下面（错位的证据比不显示更糟）。窗口完整只有两种：
  // 已翻到顶（noMoreHistory）或总量不足一页（= 本来就是全量）。
  const sessionId = useCopilot((s) => s.sessionId)
  // 组里没有答案（空组）就没有可挂裁决卡的错钡：返回 null，不靠 `answers[0]!`
  // 把「非空」这个调用方不变量偷过去
  const headId = answers[0]?.id
  const reviewTurn = useCopilot((s) =>
    headId
      ? reviewTurnOf(s.messages, headId, s.noMoreHistory || s.messages.length < HISTORY_PAGE_SIZE)
      : null,
  )
  const reviewTarget = useMemo(
    () =>
      sessionId !== null && sessionId !== '' && reviewTurn !== null
        ? { sessionId, turn: reviewTurn }
        : null,
    [sessionId, reviewTurn],
  )

  // 一组 = 一轮（见 domain/dual.ts 的 groupAnswerRuns）。组里出现几个 agent
  // kind，就说明这一轮问了几家。
  const agents = useMemo(() => distinctAgentKinds(answers), [answers])

  // 多栏：同一栏的多段 assistant 合成一条（同一个 agent 也可能拆成多段：工具
  // 调用被分段 / 停止后重发），工具按 agentKind 归到各自那栏。
  // 单栏（≤1 个 kind）不合并：那条路径的时间顺序本身就是对的。
  const merged = useMemo(
    () => (agents.length > 1 ? mergeAgentAnswers(answers, agents) : answers),
    [answers, agents],
  )

  // 多栏才把工具行从转录流里收进各栏（见 renderAnswer 的 hideTools 说明）
  const hideTools = useMemo(
    () => (agents.length > 1 ? attachedToolIds(merged) : EMPTY_HIDE_TOOLS),
    [agents.length, merged],
  )

  // 固定引用喂给 memo 过的 MultiAnswers
  const renderLane = useCallback(
    (message: ChatMessage) => renderAnswer(message, hideTools),
    [renderAnswer, hideTools],
  )

  // 单栏才聚段（见 groupToolRuns）：多栏走 MultiAnswers，不白算
  const runs = useMemo(() => (agents.length > 1 ? [] : groupToolRuns(answers)), [agents.length, answers])

  // **单栏（0 或 1 个 kind）：按原顺序渲染**，不合并、不把工具吸进气泡。
  //
  // 0 个 kind = 这一轮一条 assistant 都没有（整轮失败 / 只有工具）：照原顺序
  // 渲染，不能凭空造一个空白栏。
  // 1 个 kind = 只问了一家：多段 assistant 保持分段；工具**按到达顺序**聚成
  // chip 带（同一段里连续的几条和成一排，前后顺序即时间顺序）。
  if (agents.length <= 1) {
    return (
      <>
        {runs.map((run) =>
          'tools' in run ? (
            <ToolChipList key={run.key} tools={run.tools} />
          ) : (
            <Fragment key={run.key}>{renderAnswer(run.message, EMPTY_HIDE_TOOLS)}</Fragment>
          ),
        )}
      </>
    )
  }

  return (
    <MultiAnswers
      answers={merged}
      highlightKind={defaultAgentKind}
      renderAnswer={renderLane}
      backends={backends}
      reviewTarget={reviewTarget}
    />
  )
})
