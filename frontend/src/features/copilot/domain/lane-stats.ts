/**
 * 分栏用量账的纯计算：正文增量的采样窗口、usage 四桶的累加。
 *
 * 从 `turn-handlers.ts` 抽出（那里一个函数里混了状态路由、用量记账、改写参数缓存、
 * 跨 feature 广播四类关注点）。这里的计算与 store 无关：只吃 `TurnStats` 吐出新的
 * `TurnStats`，UI 侧的读法见同目录 `usage.ts`。
 *
 * 口径约定（与后端/pi 一致，改动前先读 types.ts 的 TurnStats 注释）：
 * - `exactTokens` 只含**输出** token（生成速度的分母），输入侧另有两桶；
 * - 每栏一份账（`turnStatsByLane`）+ 一份全局账（`turnStats`），两处分别累加。
 */

import type { TurnStats } from '../types'

/** 采样窗口：只留最近 4 秒（流式速度用 2s 窗口，更早的采样没有读者） */
const SAMPLE_WINDOW_MS = 4000

/**
 * 一帧 usage 的四个桶。
 *
 * 与 `streaming.ts` 的 `UsagePayload` 结构相同但**不 import 它**：`streaming.ts`
 * 引 `./domain`，反向引类型会让「domain 不依赖上层」这条边界只剩一句注释。
 * 结构相同即成立（调用点传 `UsagePayload` 直接可赋值）。
 */
export interface UsageBuckets {
  outputTokens: number
  inputTokens: number
  cacheReadTokens: number
  cacheWriteTokens: number
}

/** 正文增量写进**某一栏**的账：首字/末字时间与估算 token */
export function markLaneDelta(lane: TurnStats, estTokens: number, now: number): TurnStats {
  return {
    ...lane,
    // 该栏自己的首字/末字时间：多答时比较「谁先出字、谁更快」全靠它
    firstDeltaAt: lane.firstDeltaAt ?? now,
    lastDeltaAt: now,
    estTokens: lane.estTokens + estTokens,
  }
}

/** 正文增量写进**全局**账：时间戳 + 采样窗口（只留最近 4 秒） */
export function withDeltaSample(stats: TurnStats, estTokens: number, now: number): TurnStats {
  const estTotal = stats.estTokens + estTokens
  const samples = [...stats.samples, [now, estTotal] as [number, number]]
  const cutoff = now - SAMPLE_WINDOW_MS
  const start = samples.findIndex(([t]) => t >= cutoff)
  return {
    ...stats,
    firstDeltaAt: stats.firstDeltaAt ?? now,
    lastDeltaAt: now,
    estTokens: estTotal,
    samples: start > 0 ? samples.slice(start) : samples,
  }
}

/** 一帧 usage 累加进某一栏的账 */
export function addUsageToLane(lane: TurnStats, usage: UsageBuckets): TurnStats {
  return {
    ...lane,
    exactTokens: (lane.exactTokens ?? 0) + usage.outputTokens,
    inputTokens: (lane.inputTokens ?? 0) + usage.inputTokens,
    cacheReadTokens: (lane.cacheReadTokens ?? 0) + usage.cacheReadTokens,
    cacheWriteTokens: (lane.cacheWriteTokens ?? 0) + usage.cacheWriteTokens,
  }
}

/**
 * 一帧 usage 累加进全局账。
 *
 * `exactTokens` 只算输出：上一代 UI 用它展示「生成速度」，混进输入会让速度虚高数倍。
 * 输入侧成本看 input/cache 两个字段。
 */
export function addUsageToTurn(stats: TurnStats, usage: UsageBuckets): TurnStats {
  return {
    ...stats,
    exactTokens: (stats.exactTokens ?? 0) + usage.outputTokens,
    inputTokens: (stats.inputTokens ?? 0) + usage.inputTokens,
    cacheReadTokens: (stats.cacheReadTokens ?? 0) + usage.cacheReadTokens,
    cacheWriteTokens: (stats.cacheWriteTokens ?? 0) + usage.cacheWriteTokens,
  }
}
