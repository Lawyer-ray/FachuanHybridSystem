/**
 * 输出速度指示：流式期间每 250ms 刷新「≈ N tok/s」（字符启发式估算，
 * 后端流式不携带逐 token 计数）；结束后切真实值——「N tokens · 平均
 * M tok/s · 用时 Ss」（usage 事件为 pi 精确计数，未收到则仍为 ≈）。
 *
 * 与 `LaneUsageChip` 是**同一份数据的两种密度**：那边是多答栏头的一行对比
 * （速度 / 总量 / 命中率），这边是输入框脚下的一行自述（输出 token / 平均速度 /
 * 用时）。所以数字归一（`laneUsageFromStats`）与格式化（`formatTokenCount` /
 * `formatSpeed` / `formatShortSeconds`）全部走 domain/usage，两处不再各写一套
 * ——这里原先自己写了一份 `>= 100 ? 0 位 : >= 10 ? 1 位 : 2 位`，与 chip 的
 * 那份是同一套规则的两份拷贝，改一处漏一处。
 */

import { useEffect, useState } from 'react'

import {
  formatShortSeconds,
  formatSpeed,
  formatTokenCount,
  laneUsageDetail,
  laneUsageFromStats,
  laneUsageSpeed,
  tokensPerSecond,
} from '../domain'
import { useCopilot } from '../store'

export function TurnStatsView() {
  const streaming = useCopilot((s) => s.streaming)
  const stats = useCopilot((s) => s.turnStats)
  const [rate, setRate] = useState(0)

  // 实时速度在 interval 回调里算（渲染期不得调用 Date.now 这类非纯函数）
  useEffect(() => {
    if (!streaming) return
    const compute = () => setRate(tokensPerSecond(useCopilot.getState().turnStats.samples, Date.now()))
    compute()
    const timer = setInterval(compute, 250)
    return () => clearInterval(timer)
  }, [streaming])

  if (streaming) {
    if (rate <= 0 && stats.estTokens === 0) return null
    return <span className="tabular-nums">≈ {formatSpeed(rate)} tok/s</span>
  }

  if (stats.doneAt === null || stats.firstDeltaAt === null) return null
  const usage = laneUsageFromStats(stats)
  const approx = usage.estimated ? '≈ ' : ''
  // 实时路径没有首字时刻（见 LaneUsage.ttftMs），明细里只有总耗时
  const detail = laneUsageDetail(usage)
  return (
    <span className="tabular-nums" title={detail || undefined}>
      {approx}
      {formatTokenCount(usage.outputTokens ?? 0)} tokens · 平均{' '}
      {formatSpeed(laneUsageSpeed(usage) ?? 0)} tok/s · {formatShortSeconds(usage.durationMs ?? 0)}
    </span>
  )
}
