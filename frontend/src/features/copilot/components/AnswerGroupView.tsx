/**
 * 一轮回答的渲染决策：单栏（1 条）走普通气泡，多栏（2~4 条）交给 MultiAnswers
 * 并排。
 *
 * 从 MessageList 拆出（后者已到软红线）：这里同时承担三件互相关联的事——
 * 「这一轮跑了几家」的还原、同栏多段消息的合并、以及单栏/多栏的分派。它们
 * 共用一个判据，分开放两处迟早漂移（一处合并了、另一处没合并，同一轮会时
 * 而两栏时而不合并）。
 */

import { Fragment } from 'react'

import { attachedToolIds, DEFAULT_AGENT_KIND, distinctAgentKinds, mergeAgentAnswers } from '../domain'
import { useCopilot } from '../store'
import type { ChatMessage } from '../types'
import { MultiAnswers } from './MultiAnswers'

/** 单栏没有「已归位的工具」（工具行照旧平铺），共用一个空集避免每次新建 */
const EMPTY_HIDE_TOOLS: ReadonlySet<string> = new Set()

export function AnswerGroupView({
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
   */
  renderAnswer: (message: ChatMessage, hideTools: ReadonlySet<string>) => React.ReactNode
}) {
  // 栏头高亮的是「当前默认后端」：与后端清单第一项同口径（新建会话默认用它），
  // 律师据此知道哪一栏是自己平时问的那个。
  const defaultAgentKind = useCopilot((s) => s.selectedAgentKind || DEFAULT_AGENT_KIND)

  if (answers.length <= 1) return <>{renderAnswer(answers[0]!, EMPTY_HIDE_TOOLS)}</>

  // 一组 = 一轮（见 domain/dual.ts 的 groupAnswerRuns）。组里出现几个 agent
  // kind，就说明这一轮问了几家。
  const agents = distinctAgentKinds(answers)

  // **单栏（0 或 1 个 kind）：逐条按原顺序渲染**，不合并、不把工具吸进气泡。
  //
  // 0 个 kind = 这一轮一条 assistant 都没有（整轮失败 / 只有工具）：照原顺序
  // 渲染工具行，不能凭空造一个空白栏。
  // 1 个 kind = 只问了一家：行为必须与引入多栅前完全一致——工具行按时间平铺在
  // 气泡之间（多轮时间顺序本身就是对的），多段 assistant 也保持分段。
  // 走 mergeAgentAnswers 会把工具吸进气泡、把多段合并，那是多栏才需要的形态。
  if (agents.length <= 1) {
    return (
      <>
        {answers.map((message) => (
          <Fragment key={message.id}>{renderAnswer(message, EMPTY_HIDE_TOOLS)}</Fragment>
        ))}
      </>
    )
  }

  // 多栏：同一栏的多段 assistant 合成一条（同一个 agent 也可能拆成多段：工具
  // 调用被分段 / 停止后重发），工具按 agentKind 归到各自那栏。
  const merged = mergeAgentAnswers(answers, agents)

  // 多栏才把工具行从转录流里收进各栏（见 renderAnswer 的 hideTools 说明）
  const hideTools = attachedToolIds(merged)
  return (
    <MultiAnswers
      answers={merged}
      highlightKind={defaultAgentKind}
      renderAnswer={(message) => renderAnswer(message, hideTools)}
    />
  )
}
