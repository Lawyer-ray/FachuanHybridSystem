import { describe, expect, it } from 'vitest'

import { estimateTokens, tokensPerSecond } from './tokens'

describe('输出速度估算', () => {
  it('estimateTokens：CJK 约 0.7/字，ASCII 约 4 字符/token', () => {
    expect(estimateTokens('你好')).toBe(1) // 2 字 × 0.7 = 1.4 → 1
    expect(estimateTokens('abcdefgh')).toBe(2) // 8/4
    expect(estimateTokens('你好abcdefgh')).toBe(3) // 1.4 + 2 ≈ 3
    expect(estimateTokens('')).toBe(0)
  })

  it('tokensPerSecond：滑动窗口内按采样斜率计算', () => {
    const now = 10_000
    const samples: Array<[number, number]> = [
      [now - 3000, 0],
      [now - 2000, 10],
      [now - 1000, 20],
      [now, 30],
    ]
    // 窗口起点取第一个 >= now-2000 的采样（10 tokens），2 秒 +20
    expect(tokensPerSecond(samples, now)).toBeCloseTo(10, 5)
  })

  it('样本不足或时间倒挂时为 0', () => {
    expect(tokensPerSecond([], Date.now())).toBe(0)
    expect(tokensPerSecond([[1000, 5]], Date.now())).toBe(0)
    // now 早于最后一个采样（时钟回拨）时不出负数
    expect(tokensPerSecond([[1000, 5], [2000, 10]], 500)).toBe(0)
  })
})
