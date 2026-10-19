/**
 * lib/format（friendlyTime）纯逻辑单测（node 环境）。
 * 两条收敛来源的输出各自锁死：home 收件箱（cn 格式，失败回 ''）与
 * material-prep 材料卡（md 格式，失败回原串）。
 * 「今天/昨天」用本地墙上钟构造，测试机在任意时区（含 CI 的 UTC）结果一致。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { friendlyTime } from './format'

/** 固定「现在」：2026-10-18 14:30 本地 */
const NOW = new Date(2026, 9, 18, 14, 30)

const p = (n: number) => String(n).padStart(2, '0')
const hhmm = (d: Date) => `${p(d.getHours())}:${p(d.getMinutes())}`

/** 绝对时刻 → 显式 +00:00 偏移的 ISO（UTC 墙上钟原样 + 偏移，解析回同一时刻） */
function utcIsoOf(d: Date): string {
  return d.toISOString().slice(0, 16) + '+00:00'
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(NOW)
})

afterEach(() => {
  vi.useRealTimers()
})

describe('friendlyTime 默认（cn 格式，home 收件箱口径）', () => {
  it('今天 → 今天 HH:mm（补零）', () => {
    expect(friendlyTime('2026-10-18T09:05')).toBe('今天 09:05')
    expect(friendlyTime(utcIsoOf(NOW))).toBe(`今天 ${hhmm(NOW)}`)
  })

  it('昨天 → 昨天 HH:mm', () => {
    expect(friendlyTime('2026-10-17T23:59')).toBe('昨天 23:59')
    const yest = new Date(NOW)
    yest.setDate(NOW.getDate() - 1)
    expect(friendlyTime(utcIsoOf(yest))).toBe(`昨天 ${hhmm(yest)}`)
  })

  it('更早 → M 月 D 日（不补零，保持原 formatRelative 输出）', () => {
    expect(friendlyTime('2026-09-07T10:00')).toBe('9 月 7 日')
    expect(friendlyTime('2025-12-31T10:00')).toBe('12 月 31 日')
  })

  it('跨月边界（昨天是上月末）也正确判昨天', () => {
    vi.setSystemTime(new Date(2026, 9, 1, 12, 0, 0)) // 10-01，昨天是 09-30
    expect(friendlyTime('2026-09-30T18:00')).toBe('昨天 18:00')
  })

  it('非法输入回默认空串', () => {
    expect(friendlyTime('')).toBe('')
    expect(friendlyTime('not-a-date')).toBe('')
  })
})

describe('friendlyTime md 格式（material-prep 材料卡口径）', () => {
  it('今天/昨天仍是 HH:mm 前缀', () => {
    expect(friendlyTime('2026-10-18T08:00', { else: 'md' })).toBe('今天 08:00')
    expect(friendlyTime('2026-10-17T08:00', { else: 'md' })).toBe('昨天 08:00')
  })

  it('更早 → MM-dd（两位补零，保持原 timeLabel 输出）', () => {
    expect(friendlyTime('2026-09-07T10:00', { else: 'md' })).toBe('09-07')
    expect(friendlyTime('2025-12-31T10:00', { else: 'md' })).toBe('12-31')
  })

  it('解析失败回 fallback（原实现回原串）', () => {
    expect(friendlyTime('not-a-date', { else: 'md', fallback: 'not-a-date' })).toBe('not-a-date')
  })
})
