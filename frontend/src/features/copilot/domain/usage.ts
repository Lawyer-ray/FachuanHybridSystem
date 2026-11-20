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
 *
 * 两条数据来源归一：
 * - 实时：`TurnStats`（内存账，`laneUsageFromStats`）；
 * - 历史：后端落库的 `metadata.usage_by_lane` + `metadata.ttft_ms`
 *   （`laneUsageFromMetadata`——刷新后分栏用量还能亮的唯一路径）。
 * 两者都归一到 `LaneUsage`，UI 只认那一个形状。
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

/**
 * 一栏用量的**展示形状**：实时账（TurnStats）与历史落库（消息 metadata）两条
 * 来源都归一到这里，UI 只认这一个接口。
 *
 * 为什么不让 UI 直接吃 TurnStats：历史回放的数据来自后端落库的
 * `metadata.usage_by_lane`（snake_case、字段可缺、值可能是任意 JSON），实时数据
 * 来自内存里的 TurnStats（绝对时间戳、字段语义不同）。两个形状各写一套渲染写法，
 * 「栏头一个数、刷新后另一个数」这种漂移迟早发生。
 *
 * **字段一律可 null = 没这个数**（缺失与 0 是两件事）：UI 遇到 null 整段不渲染，
 * 显示「0 tok」会让律师以为这一栏真的只花了 0。
 */
export interface LaneUsage {
  /** 输出 token（生成速度的分母） */
  outputTokens: number | null
  /** 输入 token（未命中缓存部分） */
  inputTokens: number | null
  /** 缓存读 token */
  cacheReadTokens: number | null
  /** 缓存写 token */
  cacheWriteTokens: number | null
  /**
   * 首字耗时（ms）。
   *
   * 实时路径拿不到：TurnStats 只有 firstDeltaAt（绝对时刻），请求发出时刻没有
   * 记在账上，硬凑一个「首字 = 0s」就是编数。历史路径来自 `metadata.ttft_ms`。
   */
  ttftMs: number | null
  /** 总耗时（ms）。实时 = 首字→结束（与 TurnStatsView 的「用时」同口径） */
  durationMs: number | null
  /** 数值来自字符启发式估算（不是 provider 上报）：UI 必须加 `≈` */
  estimated: boolean
}

/** 四桶之和（缺的桶按 0；用于「这一栏花了多少」与「有没有东西可显示」） */
export function laneUsageTotal(usage: LaneUsage): number {
  return (
    (usage.outputTokens ?? 0) +
    (usage.inputTokens ?? 0) +
    (usage.cacheReadTokens ?? 0) +
    (usage.cacheWriteTokens ?? 0)
  )
}

/** 分栏缓存命中率（0~1）；分母含 cache 读——只除输入会把「全命中」算成 0% */
export function laneUsageCacheHitRate(usage: LaneUsage): number | null {
  const read = usage.cacheReadTokens ?? 0
  const denom = (usage.inputTokens ?? 0) + read + (usage.cacheWriteTokens ?? 0)
  if (denom <= 0) return null
  return read / denom
}

/** 分栏生成速度（输出 token / 秒）；缺输出或缺耗时时 null（不显示） */
export function laneUsageSpeed(usage: LaneUsage): number | null {
  if (usage.outputTokens === null || usage.durationMs === null) return null
  const seconds = usage.durationMs / 1000
  // 与 laneSpeed 同口径：不足 0.1s 不除，否则 3 个 token 能算出 3000 tok/s
  if (seconds < 0.1) return null
  return usage.outputTokens / seconds
}

/** TurnStats（实时账）→ 展示形状 */
export function laneUsageFromStats(stats: TurnStats): LaneUsage {
  return {
    outputTokens: outputTokens(stats),
    inputTokens: stats.inputTokens ?? null,
    cacheReadTokens: stats.cacheReadTokens ?? null,
    cacheWriteTokens: stats.cacheWriteTokens ?? null,
    ttftMs: null,
    durationMs: elapsedMs(stats),
    // 只有拿到 usage 事件才算精确；否则输出 token 是字符估算
    estimated: stats.exactTokens === null,
  }
}

/** 合法的 token 计数：有限非负数取整；字符串 / NaN / 负数 / 布尔一律视为缺失 */
function tokenCountOf(v: unknown): number | null {
  if (typeof v !== 'number' || !Number.isFinite(v) || v < 0) return null
  return Math.round(v)
}

/** 合法的毫秒值：有限正数取整；0 / 负数 / 非数字视为缺失（0ms 首字是假数） */
function positiveMsOf(v: unknown): number | null {
  if (typeof v !== 'number' || !Number.isFinite(v) || v <= 0) return null
  return Math.round(v)
}

/**
 * 后端落库的 `metadata` → 每栏用量（键 = agent kind，空串 = 单栏/未标注）。
 *
 * 契约（后端并行改造中，见报告）：assistant 消息的
 * `metadata.usage_by_lane = { [agent]: { output, input, cache_read, cache_write } }`
 * （snake_case，值为 token 整数），同一条消息另有 `metadata.ttft_ms`。
 *
 * 收窄规则（**宁缺勿错**：律师看到假数比看不到数更糟）：
 * - `usage_by_lane` 不是「对象」→ 返回 null（数组/null/字符串/缺失都算没有）；
 * - 单个栏位不是对象 → 丢掉那一栏，不影响其他栏；
 * - 桶值只接受**有限非负 number**（取整）：字符串 `"120"`、null、NaN、负数一律
 *   记为缺失——后端接口契约是整数，做字符串解析只会把脏数据变成数字；
 * - 未知字段（`cost` / `model` / 后端将来加的）全部丢弃，本函数只认四桶 + 两个耗时；
 * - 栏位四桶全空且没有首字耗时 → 丢掉那一栏（空条目在 UI 上毫无意义）；
 * - 全部栏位都被丢掉 → 返回 null；
 * - `ttft_ms` / `duration_ms`：栏位自带的优先；顶层 `metadata.ttft_ms` /
 *   `metadata.duration_ms` 只在「这一份 metadata 里只有一个栏位」时才套用
 *   （多栏时顶层耗时属于哪一栏无法确定，按缺失处理）；
 * - `duration_ms` 是**可选**扩展（后端尚未承诺）：有则亮起「速度 / 总耗时」，
 *   无则那两段整段省略——绝不拿 ttft 之外的数据推算一个出来。
 * - `estimated` 恒为 false：落库的都是 provider 上报值。
 */
export function laneUsageFromMetadata(
  metadata: Record<string, unknown> | undefined,
): Record<string, LaneUsage> | null {
  const raw = metadata?.usage_by_lane
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const out: Record<string, LaneUsage> = {}
  for (const [kind, entry] of Object.entries(raw as Record<string, unknown>)) {
    if (!entry || typeof entry !== 'object' || Array.isArray(entry)) continue
    const row = entry as Record<string, unknown>
    const usage: LaneUsage = {
      outputTokens: tokenCountOf(row.output),
      inputTokens: tokenCountOf(row.input),
      cacheReadTokens: tokenCountOf(row.cache_read),
      cacheWriteTokens: tokenCountOf(row.cache_write),
      ttftMs: positiveMsOf(row.ttft_ms),
      durationMs: positiveMsOf(row.duration_ms),
      estimated: false,
    }
    if (laneUsageTotal(usage) <= 0 && usage.ttftMs === null) continue
    out[kind] = usage
  }
  const lanes = Object.keys(out)
  if (lanes.length === 0) return null
  // 顶层耗时只在唯一栏位时套用（见上方收窄规则）
  if (lanes.length === 1) {
    const only = out[lanes[0]!]!
    const ttftMs = only.ttftMs ?? positiveMsOf(metadata?.ttft_ms)
    const durationMs = only.durationMs ?? positiveMsOf(metadata?.duration_ms)
    if (ttftMs !== only.ttftMs || durationMs !== only.durationMs) {
      out[lanes[0]!] = { ...only, ttftMs, durationMs }
    }
  }
  return out
}

/**
 * 从「一轮多栏的账」里取某一栏。
 *
 * 只做两件事：同键直取；**唯一栏位**时兜底（后端可能只写了一个栏位，而消息
 * 的 `agent_kind` 为空串——旧数据/未标注）。多栏时的键对不上就返回 null：
 * 猜错等于把 A 栏的账挂在 B 栏上，比不显示糟糕得多。
 */
export function pickLaneUsage(
  lanes: Record<string, LaneUsage> | null | undefined,
  kind: string,
): LaneUsage | null {
  if (!lanes) return null
  const exact = lanes[kind]
  if (exact) return exact
  const values = Object.values(lanes)
  return values.length === 1 ? values[0]! : null
}

/**
 * 分栏徽标的一行文字：`≈48 tok/s · 12k tok · 缓存 62%`（缺的段整段省略）。
 *
 * 估算值只加**一个**前缀 `≈` 盖住整行，而不是每个数字前面都挂一个——
 * 「≈48 tok/s · ≈12k tok」读起来像两组互不相干的估算。
 */
export function laneUsageBadge(usage: LaneUsage): string {
  const approx = usage.estimated ? '≈' : ''
  const parts: string[] = []
  const speed = laneUsageSpeed(usage)
  if (speed !== null && speed > 0) parts.push(`${formatSpeed(speed)} tok/s`)
  const total = laneUsageTotal(usage)
  if (total > 0) parts.push(`${formatTokenCount(total)} tok`)
  const hit = laneUsageCacheHitRate(usage)
  if (hit !== null) parts.push(`缓存 ${formatPercent(hit)}`)
  if (parts.length === 0) return ''
  return `${approx}${parts.join(' · ')}`
}

/**
 * 悬停明细（`title`）：模型名 + 四桶 + 首字耗时 + 总耗时（缺的段整段省略）。
 *
 * **不含金额**：后端没有 cost 字段，前端也没有单价表，拿 token 乘一个猜出来的
 * 单价必然错——律师看到的金额一旦是错的，比不显示糟得多。
 */
export function laneUsageDetail(usage: LaneUsage, model?: string | null): string {
  const approx = usage.estimated ? '≈' : ''
  // 0 与缺失同样省略：「缓存写 0 tok」在律师眼里等于「这笔真花过 0」
  const bucket = (label: string, v: number | null) =>
    v !== null && v > 0 ? `${label} ${approx}${formatTokenCount(v)} tok` : ''
  const parts = [
    model ? `模型 ${model}` : '',
    bucket('输入', usage.inputTokens),
    bucket('输出', usage.outputTokens),
    bucket('缓存读', usage.cacheReadTokens),
    bucket('缓存写', usage.cacheWriteTokens),
    usage.ttftMs !== null && usage.ttftMs > 0 ? `首字 ${formatDuration(usage.ttftMs)}` : '',
    usage.durationMs !== null && usage.durationMs > 0 ? `总耗时 ${formatDuration(usage.durationMs)}` : '',
  ]
  return parts.filter(Boolean).join(' · ')
}

/**
 * 密集版的秒数格式（**不跨分钟**）：`0.8s` / `3.0s` / `200s`。
 *
 * 为什么与 formatDuration 并存而不是合并：formatDuration 面向「一段耗时」（含
 * 分钟进位，`1m12s`），TurnStatsView 是输入框脚下一行密集文字，跨分钟进位会把
 * 「200s」变成「3m20s」，与它长期展示的口径不符（也有既有用例锁着）。两份差在
 * **分档规则**，共享同一份调用点的仍然是本文件（UI 里不再各写一遍）。
 */
export function formatShortSeconds(ms: number): string {
  const seconds = Math.max(0.1, ms / 1000)
  return seconds < 100 ? `${seconds.toFixed(1)}s` : `${Math.round(seconds)}s`
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
