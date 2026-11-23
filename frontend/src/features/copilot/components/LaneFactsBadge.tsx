/**
 * 栏头体检徽标：一眼看出这一栏「引了几条、核验过没有、是不是被截断 / 没跑成」。
 *
 * 与 `LaneUsageChip`（同一条栏头）共用一套取舍，改之前先读它：
 * - **只读消息本身**（`ChatMessage`），不订阅 store：事实是消息的函数，刷新前后
 *   同源（历史回放把 `citations` / `truncated` 都写回消息），所以历史轮次照样亮；
 * - **只有 `title` 没有浮层**：细节悬停即得，不为此再造一个弹层；
 * - **零数据整块不渲染**：空徽标等于栏头多一个看不懂的小方块（判定见
 *   `domain/lane-facts.laneFactsBadge`）。
 *
 * 为什么事实在这里算、而不是由 `MultiAnswers` 传进来：`MultiAnswers` 是栏头的
 * memo 边界（流式期间每个 delta 都会重渲），事实只依赖它已经在渲染的那条消息；
 * 放在本组件里算，那条边界与 props 一个都不用动。
 *
 * 为什么不显示分数：分数需要一个口径（引用几条算好、几个工具算够），任何口径都是
 * 产品判断；栏头只陈述事实，判断留给律师（口径见 `domain/lane-facts` 顶部注释）。
 */

import { memo } from 'react'

import { laneFactsBadge, laneFactsDetail, laneFactsOf } from '../domain'
import type { ChatMessage } from '../types'

export const LaneFactsBadge = memo(function LaneFactsBadge({ message }: { message: ChatMessage }) {
  const facts = laneFactsOf(message)
  const badge = laneFactsBadge(facts)
  if (!badge) return null
  return (
    <span
      className="ml-1 flex-none cursor-default text-[10px] text-muted-foreground/80 tabular-nums"
      title={laneFactsDetail(facts)}
      data-testid={`lane-facts-${message.agentKind || 'default'}`}
    >
      {badge}
    </span>
  )
})
