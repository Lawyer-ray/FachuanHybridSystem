/**
 * 分栏用量小徽标：挂在多答栏头，回答「这一栏花了多少、多快、缓存命中多少」。
 *
 * 为什么单独订阅 store 而不是由 `MultiAnswers` 传参：栏头是多答的 memo 边界
 * （`MultiAnswers` 只在 answers 变化时重渲），用量是高频变化的另一条数据流；
 * 放进来会让整块栏头随每次 usage 事件重渲，等于把 memo 拆了。每个 chip 只
 * 订阅自己那一栏的账，谁变谁重渲。
 *
 * 为什么只有 `title` 没有浮层：律师的用法是「扫一眼谁更便宜」，浮层要点开、
 * 要定位、要关，收益不抵成本；细节放 `title`，需要时悬停即可。
 * 金额一律不显示——前端没有单价表，拿 token 乘单价必然错（后端也无 cost 列）。
 *
 * 两种数据来源（与 domain/usage 的 `LaneUsage` 一一对应）：
 * - 实时：本轮的 `turnStatsByLane[kind]`（每轮开头清空，见 store/turn-send.ts）；
 * - 历史：调用方把落库的用量按 `usage` 传进来（`laneUsageFromMetadata` 的产物）。
 *   传了就优先用它——**刷新后能不能看见分栏用量，就看有没有人接这条线**。
 */

import type { ChatMessage } from '../types'
import { useCopilot } from '../store'
import {
  laneUsageBadge,
  laneUsageDetail,
  laneUsageFromStats,
  laneUsageTotal,
  type LaneUsage,
} from '../domain'

/**
 * 这一栏最近一次回答用的模型名（与栏头「agent · 模型」同源：`ChatMessage.model`）。
 *
 * 为什么不从 props 传：`MultiAnswers` 已经把 model 交给 `AgentModelHead` 了，但
 * 它不在本组件的调用契约里（改动会扩散到多答的栏头渲染）；而「这一栏用哪个模型
 * 答的」在转录里本来就有唯一一份数据——最近那条同 agentKind 的 assistant 气泡。
 * 实时轮次与历史回放都写这个字段（历史来自 `metadata.model`），所以两条路都亮。
 *
 * 选择器返回**字符串**（不是数组/对象），同一模型期间不会触发重渲。
 */
function lastModelOfLane(messages: ChatMessage[], kind: string): string | undefined {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i]
    if (m?.role === 'assistant' && (m.agentKind ?? '') === kind && m.model) return m.model
  }
  return undefined
}

export function LaneUsageChip({ kind, usage }: { kind: string; usage?: LaneUsage | null }) {
  // 键口径与 turn-handlers.bumpLane 一致：空串 = 单栏/未标注来源
  const stats = useCopilot((s) => s.turnStatsByLane[kind])
  const model = useCopilot((s) => lastModelOfLane(s.messages, kind))

  // 历史用量优先：调用方给了就用，不给才回落到本轮内存账
  const resolved = usage ?? (stats ? laneUsageFromStats(stats) : null)
  // 一个数都没有时不渲染整块（空徽标等于栏头多一个看不懂的小方块）
  if (!resolved || laneUsageTotal(resolved) <= 0) return null
  const badge = laneUsageBadge(resolved)
  if (!badge) return null

  return (
    <span
      className="ml-1 flex-none cursor-default text-[10px] text-muted-foreground/80 tabular-nums"
      title={laneUsageDetail(resolved, model)}
      data-testid={`lane-usage-${kind || 'default'}`}
    >
      {badge}
    </span>
  )
}
