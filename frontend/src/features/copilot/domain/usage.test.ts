import { describe, expect, it } from 'vitest'

import type { TurnStats } from '../types'
import {
  cacheHitRate,
  elapsedMs,
  emptyTurnStats,
  formatDuration,
  formatPercent,
  formatShortSeconds,
  formatSpeed,
  formatTokenCount,
  laneSpeed,
  laneUsageBadge,
  laneUsageCacheHitRate,
  laneUsageDetail,
  laneUsageFromMetadata,
  laneUsageFromStats,
  laneUsageSpeed,
  laneUsageTotal,
  outputTokens,
  pickLaneUsage,
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

  it('密集秒数不跨分钟（与 formatDuration 的分档是两回事）', () => {
    expect(formatShortSeconds(820)).toBe('0.8s')
    expect(formatShortSeconds(3000)).toBe('3.0s')
    expect(formatShortSeconds(59_000)).toBe('59.0s')
    // 200s 不能变成 3m20s：这是输入框脚下那行一直以来的口径
    expect(formatShortSeconds(200_000)).toBe('200s')
    // 0ms 不能显示「0.0s」那样的假精度，下限 0.1s
    expect(formatShortSeconds(0)).toBe('0.1s')
  })
})

describe('laneUsageFromMetadata：历史落库的用量收窄', () => {
  it('正常形状（snake_case 四桶）收到 LaneUsage', () => {
    const lanes = laneUsageFromMetadata({
      usage_by_lane: {
        pi: { output: 120, input: 300, cache_read: 900, cache_write: 30 },
      },
      ttft_ms: 850,
    })
    expect(lanes).not.toBeNull()
    expect(lanes!.pi).toEqual({
      outputTokens: 120,
      inputTokens: 300,
      cacheReadTokens: 900,
      cacheWriteTokens: 30,
      // 唯一栏位 → 顶层 ttft_ms 归它
      ttftMs: 850,
      durationMs: null,
      estimated: false,
    })
  })

  it('多栏：顶层 ttft_ms 不硬套（属谁无法确定，按缺失处理）', () => {
    const lanes = laneUsageFromMetadata({
      usage_by_lane: {
        pi: { output: 10, input: 1, cache_read: 0, cache_write: 0 },
        dsh: { output: 20, input: 2, cache_read: 0, cache_write: 0 },
      },
      ttft_ms: 500,
    })!
    expect(lanes.pi!.ttftMs).toBeNull()
    expect(lanes.dsh!.ttftMs).toBeNull()
  })

  it('栏位自带的 ttft_ms 优先于顶层', () => {
    const lanes = laneUsageFromMetadata({
      usage_by_lane: { pi: { output: 5, ttft_ms: 320 } },
      ttft_ms: 999,
    })!
    expect(lanes.pi!.ttftMs).toBe(320)
  })

  it('缺失/畸形一律 null（宁缺勿错，不编造）', () => {
    // 完全没有 usage_by_lane
    expect(laneUsageFromMetadata(undefined)).toBeNull()
    expect(laneUsageFromMetadata({})).toBeNull()
    // 不是对象：数组 / null / 字符串 / 数字
    expect(laneUsageFromMetadata({ usage_by_lane: [] })).toBeNull()
    expect(laneUsageFromMetadata({ usage_by_lane: null })).toBeNull()
    expect(laneUsageFromMetadata({ usage_by_lane: 'pi:120' })).toBeNull()
    expect(laneUsageFromMetadata({ usage_by_lane: 7 })).toBeNull()
    // 空对象 → 没有可用栏位
    expect(laneUsageFromMetadata({ usage_by_lane: {} })).toBeNull()
    // 栏位不是对象 → 整栏丢掉
    expect(laneUsageFromMetadata({ usage_by_lane: { pi: 120 } })).toBeNull()
    expect(laneUsageFromMetadata({ usage_by_lane: { pi: null } })).toBeNull()
    expect(laneUsageFromMetadata({ usage_by_lane: { pi: [120] } })).toBeNull()
  })

  it('桶值只接受有限非负数字：字符串/负数/NaN/Infinity 记为缺失', () => {
    const lanes = laneUsageFromMetadata({
      usage_by_lane: {
        pi: {
          output: '120', // 字符串不解析（契约就是整数）
          input: -1,
          cache_read: Number.NaN,
          cache_write: Number.POSITIVE_INFINITY,
        },
      },
    })
    // 四桶全空、也没有首字 → 整栏没有意义，返回 null
    expect(lanes).toBeNull()

    const mixed = laneUsageFromMetadata({
      usage_by_lane: { pi: { output: 12.6, input: '30', cache_read: 0 } },
    })!
    expect(mixed.pi!.outputTokens).toBe(13) // 取整
    expect(mixed.pi!.inputTokens).toBeNull()
    expect(mixed.pi!.cacheReadTokens).toBe(0) // 0 是「真的 0」，不是缺失
    expect(mixed.pi!.cacheWriteTokens).toBeNull()
  })

  it('未知字段丢弃（cost / model / 后端将来加的都不认）', () => {
    const lanes = laneUsageFromMetadata({
      usage_by_lane: {
        pi: { output: 10, cost: 0.42, model: 'gpt-x', nested: { output: 999 } },
        model: 'gpt-x',
      },
    })!
    expect(Object.keys(lanes)).toEqual(['pi'])
    expect(lanes.pi).toEqual({
      outputTokens: 10,
      inputTokens: null,
      cacheReadTokens: null,
      cacheWriteTokens: null,
      ttftMs: null,
      durationMs: null,
      estimated: false,
    })
  })

  it('duration_ms 是可选扩展：有则亮起，无则 null（不推算）', () => {
    // 栏位自带
    expect(
      laneUsageFromMetadata({ usage_by_lane: { pi: { output: 10, duration_ms: 2400 } } })!.pi!
        .durationMs,
    ).toBe(2400)
    // 顶层（唯一栏位时套用，与 ttft_ms 同一条规则）
    expect(
      laneUsageFromMetadata({ usage_by_lane: { pi: { output: 10 } }, duration_ms: 8000 })!.pi!
        .durationMs,
    ).toBe(8000)
    // 多栏时不硬套
    expect(
      laneUsageFromMetadata({
        usage_by_lane: { pi: { output: 10 }, dsh: { output: 20 } },
        duration_ms: 8000,
      })!.dsh!.durationMs,
    ).toBeNull()
    // 压根没有
    expect(laneUsageFromMetadata({ usage_by_lane: { pi: { output: 10 } } })!.pi!.durationMs).toBeNull()
  })

  it('多栏只丢畸形的那个，好栏照常产出', () => {
    const lanes = laneUsageFromMetadata({
      usage_by_lane: { pi: { output: 10 }, dsh: 'nope' },
    })!
    expect(Object.keys(lanes)).toEqual(['pi'])
  })
})

describe('pickLaneUsage：一轮多栏里取自己那份', () => {
  const lanes = {
    pi: laneUsageFromStats(stats({ exactTokens: 10 })),
    dsh: laneUsageFromStats(stats({ exactTokens: 20 })),
  }

  it('同键直取', () => {
    expect(pickLaneUsage(lanes, 'dsh')!.outputTokens).toBe(20)
  })

  it('查不到且多栏 → null（不猜，猜错等于把 A 栏的账挂到 B 栏）', () => {
    expect(pickLaneUsage(lanes, 'oai')).toBeNull()
    expect(pickLaneUsage(lanes, '')).toBeNull()
  })

  it('唯一栏位时兜底（旧数据/未标注 agent_kind）', () => {
    expect(pickLaneUsage({ pi: lanes.pi }, '')!.outputTokens).toBe(10)
  })

  it('没有账时 null', () => {
    expect(pickLaneUsage(null, 'pi')).toBeNull()
    expect(pickLaneUsage(undefined, 'pi')).toBeNull()
  })
})

describe('实时账 → LaneUsage', () => {
  it('精确 usage 事件：estimated=false，耗时 = 首字→结束，首字耗时未知', () => {
    const usage = laneUsageFromStats(
      stats({ firstDeltaAt: 1000, doneAt: 5000, exactTokens: 200, inputTokens: 50, cacheReadTokens: 950 }),
    )
    expect(usage.estimated).toBe(false)
    expect(usage.durationMs).toBe(4000)
    // 请求发出时刻没记在账上 → 不编一个 0ms
    expect(usage.ttftMs).toBeNull()
    expect(laneUsageTotal(usage)).toBe(1200)
    expect(laneUsageSpeed(usage)).toBe(50)
    expect(laneUsageCacheHitRate(usage)).toBeCloseTo(950 / 1000, 5)
  })

  it('只有字符估算：estimated=true（UI 必须加 ≈）', () => {
    const usage = laneUsageFromStats(stats({ estTokens: 80, firstDeltaAt: 0, doneAt: 2000 }))
    expect(usage.estimated).toBe(true)
    expect(usage.outputTokens).toBe(80)
  })

  it('没有输入侧数据时命中率 null（不显示 0%）', () => {
    expect(laneUsageCacheHitRate(laneUsageFromStats(stats({ exactTokens: 10 })))).toBeNull()
  })

  it('命中率分母含 cache 读（只除输入会把全命中算成 0%）', () => {
    const usage = laneUsageFromStats(
      stats({ exactTokens: 1, inputTokens: 0, cacheReadTokens: 600, cacheWriteTokens: 200 }),
    )
    expect(laneUsageCacheHitRate(usage)).toBeCloseTo(0.75, 5)
  })

  it('缺输出或缺耗时时不算速度（不足 0.1s 也不除，避免爆表）', () => {
    expect(laneUsageSpeed(laneUsageFromStats(stats()))).toBeNull()
    expect(laneUsageSpeed(laneUsageFromStats(stats({ firstDeltaAt: 0, doneAt: 50, exactTokens: 40 })))).toBeNull()
  })
})

describe('两种密度共用同一份格式化', () => {
  const usage = laneUsageFromStats(
    stats({ firstDeltaAt: 0, doneAt: 5000, exactTokens: 240, inputTokens: 100, cacheReadTokens: 900 }),
  )

  it('徽标：速度 · 总量 · 命中率，缺段整段省略', () => {
    // 240 tok / 5s = 48 tok/s；总量 240+100+900 = 1240 → 1.2k；命中 900/1000 = 90%
    expect(laneUsageBadge(usage)).toBe('48.0 tok/s · 1.2k tok · 缓存 90%')
    // 没有输入侧数据 → 不出现「缓存 0%」这种段
    expect(laneUsageBadge(laneUsageFromStats(stats({ exactTokens: 3 })))).toBe('3 tok')
    // 一个数都没有 → 空串（调用方据此不渲染整块）
    expect(laneUsageBadge(laneUsageFromStats(stats()))).toBe('')
  })

  it('估算值只在整行前加一个 ≈，不逐段重复', () => {
    const est = laneUsageFromStats(stats({ estTokens: 1200, firstDeltaAt: 0, doneAt: 4000 }))
    const badge = laneUsageBadge(est)
    expect(badge.startsWith('≈')).toBe(true)
    expect(badge.match(/≈/g)).toHaveLength(1)
  })

  it('明细：模型 + 四桶 + 首字 + 总耗时，不含金额', () => {
    const detail = laneUsageDetail(
      laneUsageFromStats(
        stats({
          firstDeltaAt: 0,
          doneAt: 5000,
          exactTokens: 240,
          inputTokens: 100,
          cacheReadTokens: 900,
          cacheWriteTokens: 10,
        }),
      ),
      'claude-sonnet',
    )
    expect(detail).toBe(
      '模型 claude-sonnet · 输入 100 tok · 输出 240 tok · 缓存读 900 tok · 缓存写 10 tok · 总耗时 5.0s',
    )
    // 后端没有 cost 字段，前端也不拿单价乘
    expect(detail).not.toMatch(/元|¥|cost|\$/)
  })

  it('明细：缺的段不渲染（不堆 0 / —）', () => {
    expect(laneUsageDetail(laneUsageFromStats(stats({ exactTokens: 7 })))).toBe('输出 7 tok')
    // 0 桶与缺失同样省略
    expect(
      laneUsageDetail(
        laneUsageFromStats(stats({ exactTokens: 7, inputTokens: 0, cacheReadTokens: 0 })),
      ),
    ).toBe('输出 7 tok')
  })

  it('明细：估算值每个 token 数都带 ≈（明细是逐项列举，必须逐项标）', () => {
    const detail = laneUsageDetail(laneUsageFromStats(stats({ estTokens: 80, inputTokens: 20 })))
    expect(detail).toBe('输入 ≈20 tok · 输出 ≈80 tok')
  })
})
