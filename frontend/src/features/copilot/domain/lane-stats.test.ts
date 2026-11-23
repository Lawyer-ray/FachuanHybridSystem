/**
 * 分栏用量账的纯计算（node 单测，不涉 DOM）。
 *
 * 要锁住的事实：
 * 1. **采样只留最近 4 秒**：更早的采样没有读者，不裁会让每一帧都拖着整轮的历史；
 * 2. **裁的是窗口外、保的是边界**：`t === now - 4000` 那一帧仍在窗口内；
 * 3. **首字时间只落一次**：多答时「谁先出字」靠它，后续 delta 不得覆盖；
 * 4. **栏账与全局账各算各的**：`exactTokens` 只累输出，输入侧三桶另计。
 */

import { describe, expect, it } from 'vitest'

import type { TurnStats } from '../types'
import { addUsageToLane, addUsageToTurn, markLaneDelta, withDeltaSample } from './lane-stats'
import { emptyTurnStats } from './usage'

function stats(over: Partial<TurnStats> = {}): TurnStats {
  return { ...emptyTurnStats(), ...over }
}

describe('withDeltaSample（全局账：时间戳 + 4 秒采样窗口）', () => {
  it('窗口外的旧样本被 slice 掉，边界那一帧保留', () => {
    // 三帧采样：6000-4000=2000 是窗口下界，1999 在界外、2000 恰好压在边界上
    const before = stats({
      samples: [
        [1000, 10],
        [1999, 10],
        [2000, 20],
      ],
      estTokens: 20,
    })
    const next = withDeltaSample(before, 5, 6000)
    // cutoff = 2000：1000 与 1999 被裁掉；2000 恰好 `t >= cutoff`，保留
    expect(next.samples).toEqual([
      [2000, 20],
      [6000, 25],
    ])
    expect(next.estTokens).toBe(25)
  })

  it('全部采样都在窗口内时原样追加（不白拷一次数组尾部）', () => {
    const next = withDeltaSample(stats({ samples: [[4000, 4]], estTokens: 4 }), 1, 5000)
    expect(next.samples).toEqual([
      [4000, 4],
      [5000, 5],
    ])
  })

  it('首字时间只落一次，末字时间与估算 token 每帧推进', () => {
    const started = withDeltaSample(stats(), 7, 1000)
    expect(started.firstDeltaAt).toBe(1000)
    expect(started.lastDeltaAt).toBe(1000)

    const later = withDeltaSample(started, 3, 3000)
    expect(later.firstDeltaAt).toBe(1000)
    expect(later.lastDeltaAt).toBe(3000)
    expect(later.estTokens).toBe(10)
  })
})

describe('markLaneDelta（某一栏的账）', () => {
  it('只记本栏的首字/末字与估算 token，不带采样点', () => {
    const lane = markLaneDelta(stats(), 12, 7000)
    expect(lane.firstDeltaAt).toBe(7000)
    expect(lane.lastDeltaAt).toBe(7000)
    expect(lane.estTokens).toBe(12)
    expect(lane.samples).toEqual([])

    const again = markLaneDelta(lane, 3, 7500)
    expect(again.firstDeltaAt).toBe(7000)
    expect(again.lastDeltaAt).toBe(7500)
    expect(again.estTokens).toBe(15)
  })
})

describe('addUsageToLane / addUsageToTurn（usage 四桶累加）', () => {
  const usage = { outputTokens: 5, inputTokens: 100, cacheReadTokens: 800, cacheWriteTokens: 50 }

  it('栏账累加四桶；exactTokens 起始为 null 时按 0 起算', () => {
    const once = addUsageToLane(stats(), usage)
    expect(once.exactTokens).toBe(5)
    expect(once.inputTokens).toBe(100)
    expect(once.cacheReadTokens).toBe(800)
    expect(once.cacheWriteTokens).toBe(50)

    const twice = addUsageToLane(once, usage)
    expect(twice.exactTokens).toBe(10)
    expect(twice.inputTokens).toBe(200)
    expect(twice.cacheReadTokens).toBe(1600)
    expect(twice.cacheWriteTokens).toBe(100)
  })

  it('全局账同样只把输出计入 exactTokens（生成速度的分母不混输入）', () => {
    const turn = addUsageToTurn(addUsageToTurn(stats(), usage), {
      outputTokens: 3,
      inputTokens: 20,
      cacheReadTokens: 900,
      cacheWriteTokens: 0,
    })
    expect(turn.exactTokens).toBe(8)
    expect(turn.inputTokens).toBe(120)
    expect(turn.cacheReadTokens).toBe(1700)
    expect(turn.cacheWriteTokens).toBe(50)
    // 两处各自累加：同一帧写栏账不会顺带改全局账
    expect(addUsageToLane(stats(), usage).exactTokens).toBe(5)
  })
})
