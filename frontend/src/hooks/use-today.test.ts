/**
 * useToday 的零点调度单测（node 环境，无需 DOM）。
 *
 * 守的是「不再用 60s 常驻轮询」这件事：定时器必须精确排到下一个零点，
 * 且不能把 24h 写死（夏令时切换日零点间隔不是 24 小时）。
 */
import { describe, expect, it } from 'vitest'

import { msUntilMidnight } from './use-today'

describe('msUntilMidnight', () => {
  it('普通一天的午夜前 1 小时：正好 1 小时', () => {
    const now = new Date(2026, 2, 10, 23, 0, 0, 0)
    expect(msUntilMidnight(now)).toBe(60 * 60 * 1000)
  })

  it('刚过零点：返回到次日零点的整 24 小时（不是 0）', () => {
    const now = new Date(2026, 2, 10, 0, 0, 0, 0)
    expect(msUntilMidnight(now)).toBe(24 * 60 * 60 * 1000)
  })

  it('零点前 1 毫秒：返回 1', () => {
    const now = new Date(2026, 2, 10, 23, 59, 59, 999)
    expect(msUntilMidnight(now)).toBe(1)
  })

  it('按本地下一个零点算，跨月也对（1 月 31 日 → 2 月 1 日）', () => {
    const now = new Date(2026, 0, 31, 20, 0, 0, 0)
    expect(msUntilMidnight(now)).toBe(4 * 60 * 60 * 1000)
  })
})
