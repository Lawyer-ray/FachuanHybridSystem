/**
 * 用量与人读格式化的纯逻辑（无 React、无 IO）。
 *
 * 存在理由：多答（2~4 栏并排）的核心价值是**比较**——可只并排显示几份答案、
 * 却看不出哪份更贵更慢，比较就只剩「读起来顺不顺」。这里把每栏的
 * token/耗时/缓存命中率算成可展示的数字，UI 只负责排版。
 *
 * 口径约定（与后端/pi 一致，改动前先读 types.ts 的 TurnStats 注释）：
 * - `exactTokens` 只含**输出** token（生成速度的分母），输入侧另有两桶；
 * - 缓存命中率 = cacheRead / (input + cacheRead + cacheWrite)；
 * - 金额**不在这里算**：前端没有单价表，用 token 乘单价必然错（后端也没有
 *   cost 列），宁可不显示也不显示错的。
 */

import type { TurnStats } from '../types'

/** 一轮统计的初值（send 入列时复位；store 与 turn-handlers 共用同一份形状） */
export function emptyTurnStats(): TurnStats {
  return {
    firstDeltaAt: null,
    lastDeltaAt: null,
    doneAt: null,
    estTokens: 0,
    exactTokens: null,
    samples: [],
  }
}

/** 输出 token（精确值优先，未上报时用字符启发式估算） */
export function outputTokens(stats: TurnStats): number {
  return stats.exactTokens ?? stats.estTokens
}

/** 总 token（输出 + 输入 + 缓存读 + 缓存写；缺省桶按 0） */
export function totalTokens(stats: TurnStats): number {
  return (
    outputTokens(stats) +
    (stats.inputTokens ?? 0) +
    (stats.cacheReadTokens ?? 0) +
    (stats.cacheWriteTokens ?? 0)
  )
}

/** 生成耗时（首字 → 结束；流未结束用最近一次 delta 兜底） */
export function elapsedMs(stats: TurnStats): number {
  if (stats.firstDeltaAt === null) return 0
  const end = stats.doneAt ?? stats.lastDeltaAt ?? stats.firstDeltaAt
  return Math.max(0, end - stats.firstDeltaAt)
}

/** 生成速度（输出 token / 秒；不足 0.1s 不除，避免爆表） */
export function laneSpeed(stats: TurnStats): number {
  const seconds = elapsedMs(stats) / 1000
  if (seconds < 0.1) return 0
  return outputTokens(stats) / seconds
}

/** 缓存命中率（0~1）；没有任何输入侧数据时返回 null（UI 不显示，而不是显示 0%） */
export function cacheHitRate(stats: TurnStats): number | null {
  const read = stats.cacheReadTokens ?? 0
  const denom = (stats.inputTokens ?? 0) + read + (stats.cacheWriteTokens ?? 0)
  if (denom <= 0) return null
  return read / denom
}

/** token 数的人读格式：998 / 1.2k / 12k / 1.2M */
export function formatTokenCount(n: number): string {
  const v = Math.max(0, Math.round(n))
  if (v < 1000) return String(v)
  if (v < 10_000) return `${(v / 1000).toFixed(1)}k`
  if (v < 1_000_000) return `${Math.round(v / 1000)}k`
  return `${(v / 1_000_000).toFixed(1)}M`
}

/** 速度人读格式：两位有效档（与 TurnStatsView 的既有口径一致） */
export function formatSpeed(tokensPerSecond: number): string {
  if (!Number.isFinite(tokensPerSecond) || tokensPerSecond <= 0) return '0'
  if (tokensPerSecond >= 100) return tokensPerSecond.toFixed(0)
  if (tokensPerSecond >= 10) return tokensPerSecond.toFixed(1)
  return tokensPerSecond.toFixed(2)
}

/** 时长人读格式：820ms / 3.4s / 1m12s */
export function formatDuration(ms: number): string {
  if (ms <= 0) return '0s'
  if (ms < 1000) return `${Math.round(ms)}ms`
  const seconds = ms / 1000
  if (seconds < 10) return `${seconds.toFixed(1)}s`
  if (seconds < 60) return `${Math.round(seconds)}s`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}m${String(s).padStart(2, '0')}s`
}

/** 百分比：0.6234 → 62% */
export function formatPercent(ratio: number): string {
  return `${Math.round(Math.max(0, Math.min(1, ratio)) * 100)}%`
}

/** 一栏的摘要（UI 用一次算好，避免渲染里反复算） */
export interface LaneSummary {
  output: number
  total: number
  speed: number
  hitRate: number | null
  durationMs: number
  /** 是否已有精确 usage（否则 token 数是字符估算，UI 要加 ≈） */
  exact: boolean
}

export function summarizeLane(stats: TurnStats): LaneSummary {
  return {
    output: outputTokens(stats),
    total: totalTokens(stats),
    speed: laneSpeed(stats),
    hitRate: cacheHitRate(stats),
    durationMs: elapsedMs(stats),
    exact: stats.exactTokens !== null,
  }
}
