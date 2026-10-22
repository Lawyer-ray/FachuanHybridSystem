/**
 * 输出速度指示：流式期间每 250ms 刷新「≈ N tok/s」（字符启发式估算，
 * 后端流式不携带逐 token 计数）；结束后切真实值——「N tokens · 平均
 * M tok/s · 用时 Ss」（usage 事件为 pi 精确计数，未收到则仍为 ≈）。
 */

import { useEffect, useState } from 'react'

import { tokensPerSecond } from '../domain'
import { useCopilot } from '../store'

function formatRate(rate: number): string {
  return rate >= 100 ? rate.toFixed(0) : rate >= 10 ? rate.toFixed(1) : rate.toFixed(2)
}

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
    return <span className="tabular-nums">≈ {formatRate(rate)} tok/s</span>
  }

  if (stats.doneAt === null || stats.firstDeltaAt === null) return null
  const tokens = stats.exactTokens ?? stats.estTokens
  const approx = stats.exactTokens === null ? '≈ ' : ''
  const endAt = stats.doneAt ?? stats.lastDeltaAt ?? stats.firstDeltaAt
  const seconds = Math.max(0.1, (endAt - stats.firstDeltaAt) / 1000)
  return (
    <span className="tabular-nums">
      {approx}
      {tokens} tokens · 平均 {formatRate(tokens / seconds)} tok/s · {seconds < 100 ? seconds.toFixed(1) : Math.round(seconds)}s
    </span>
  )
}
