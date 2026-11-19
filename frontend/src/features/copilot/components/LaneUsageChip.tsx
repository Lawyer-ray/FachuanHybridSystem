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
 */

import { useCopilot } from '../store'
import { formatDuration, formatPercent, formatSpeed, formatTokenCount, summarizeLane } from '../domain'

export function LaneUsageChip({ kind }: { kind: string }) {
  // 键口径与 turn-handlers.bumpLane 一致：空串 = 单栏/未标注来源
  const stats = useCopilot((s) => s.turnStatsByLane[kind])

  if (!stats) return null
  const lane = summarizeLane(stats)
  if (lane.total <= 0) return null

  const approx = lane.exact ? '' : '≈ '
  const speed = lane.speed > 0 ? ` · ${formatSpeed(lane.speed)} tok/s` : ''
  const detail = [
    `输出 ${approx}${formatTokenCount(lane.output)} tok`,
    `输入 ${formatTokenCount(stats.inputTokens ?? 0)} tok`,
    `缓存读 ${formatTokenCount(stats.cacheReadTokens ?? 0)} tok`,
    `缓存写 ${formatTokenCount(stats.cacheWriteTokens ?? 0)} tok`,
    lane.hitRate !== null ? `缓存命中 ${formatPercent(lane.hitRate)}` : '缓存命中 —',
    lane.durationMs > 0 ? `耗时 ${formatDuration(lane.durationMs)}` : '',
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <span
      className="ml-1 flex-none cursor-default text-[10px] text-muted-foreground/80 tabular-nums"
      title={detail}
      data-testid={`lane-usage-${kind || 'default'}`}
    >
      {approx}
      {formatTokenCount(lane.total)} tok{speed}
    </span>
  )
}
