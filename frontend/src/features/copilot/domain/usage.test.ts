import { describe, expect, it } from 'vitest'

import type { TurnStats } from '../types'
import {
  cacheHitRate,
  elapsedMs,
  emptyTurnStats,
  formatDuration,
  formatPercent,
  formatSpeed,
  formatTokenCount,
  laneSpeed,
  outputTokens,
  summarizeLane,
  totalTokens,
} from './usage'

function stats(over: Partial<TurnStats> = {}): TurnStats {
  return { ...emptyTurnStats(), ...over }
}

describe('token 口径', () => {
  it('exactTokens 只算输出，输入与缓存另计', () => {
    const s = stats({ exactTokens: 100, inputTokens: 20, cacheReadTokens: 800, cacheWriteTokens: 0 })
    expect(outputTokens(s)).toBe(100)
    expect(totalTokens(s)).toBe(920)
  })

  it('未收到 usage 时退回字符估算（此时数值带 ≈）', () => {
    const s = stats({ estTokens: 42 })
    expect(outputTokens(s)).toBe(42)
    expect(summarizeLane(s).exact).toBe(false)
  })

  it('缓存命中率分母含三桶；全空返回 null（不显示 0%）', () => {
    expect(cacheHitRate(stats())).toBeNull()
    expect(
      cacheHitRate(stats({ inputTokens: 200, cacheReadTokens: 600, cacheWriteTokens: 200 })),
    ).toBeCloseTo(0.6, 5)
  })
})

describe('耗时与速度', () => {
  it('首字到结束；流未结束时用最近 delta 兜底', () => {
    expect(elapsedMs(stats({ firstDeltaAt: 1000, lastDeltaAt: 4000 }))).toBe(3000)
    expect(elapsedMs(stats({ firstDeltaAt: 1000, lastDeltaAt: 4000, doneAt: 5000 }))).toBe(4000)
    expect(elapsedMs(stats())).toBe(0)
  })

  it('速度 = 输出 token / 秒；不足 0.1s 不除（避免爆表）', () => {
    expect(laneSpeed(stats({ firstDeltaAt: 0, doneAt: 2000, exactTokens: 40 }))).toBe(20)
    expect(laneSpeed(stats({ firstDeltaAt: 0, doneAt: 50, exactTokens: 40 }))).toBe(0)
  })
})

describe('人读格式', () => {
  it('token 数分档', () => {
    expect(formatTokenCount(0)).toBe('0')
    expect(formatTokenCount(998)).toBe('998')
    expect(formatTokenCount(1234)).toBe('1.2k')
    expect(formatTokenCount(12_345)).toBe('12k')
    expect(formatTokenCount(1_234_567)).toBe('1.2M')
  })

  it('速度与时长', () => {
    expect(formatSpeed(0)).toBe('0')
    expect(formatSpeed(3.456)).toBe('3.46')
    expect(formatSpeed(12.34)).toBe('12.3')
    expect(formatSpeed(123.4)).toBe('123')
    expect(formatDuration(820)).toBe('820ms')
    expect(formatDuration(3400)).toBe('3.4s')
    expect(formatDuration(59_000)).toBe('59s')
    expect(formatDuration(72_000)).toBe('1m12s')
  })

  it('百分比夹到 0~1', () => {
    expect(formatPercent(0.6234)).toBe('62%')
    expect(formatPercent(-1)).toBe('0%')
    expect(formatPercent(2)).toBe('100%')
  })
})
