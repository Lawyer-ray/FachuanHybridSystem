/**
 * lib/format（friendlyTime / formatBytes）纯逻辑单测（node 环境）。
 * 两条收敛来源的输出各自锁死：home 收件箱（cn 格式，失败回 ''）与
 * material-prep 材料卡（md 格式，失败回原串）。
 * 「今天/昨天」用本地墙上钟构造，测试机在任意时区（含 CI 的 UTC）结果一致。
 *
 * formatBytes 是 4 份手写实现的收敛目标，重点锁「有 GB 档」：漏 GB 的那两份
 * 会把 500MB 显示成「512000.0MB」。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { formatBytes, friendlyTime } from './format'

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

describe('formatBytes（字节 → 人类可读）', () => {
  const KB = 1024
  const MB = 1024 * KB
  const GB = 1024 * MB

  it('0 / 负数 / NaN 都回 0B', () => {
    expect(formatBytes(0)).toBe('0B')
    expect(formatBytes(-1)).toBe('0B')
    expect(formatBytes(Number.NaN)).toBe('0B')
  })

  it('B 档（<1KB）取整；KB 档下限 1（round 后不会出现 0KB）', () => {
    expect(formatBytes(1)).toBe('1B')
    expect(formatBytes(999)).toBe('999B')
    expect(formatBytes(1023)).toBe('1023B')
    // 落在 KB 档的下限：1~1.5KB 取整为 1，不会因为 round 掉到「0KB」
    expect(formatBytes(KB)).toBe('1KB')
  })

  it('KB 档四舍五入到整数', () => {
    expect(formatBytes(KB)).toBe('1KB')
    expect(formatBytes(2048)).toBe('2KB')
    expect(formatBytes(512 * KB)).toBe('512KB')
    expect(formatBytes(1.4 * KB)).toBe('1KB')
    expect(formatBytes(1.6 * KB)).toBe('2KB')
  })

  it('MB 档保留一位小数', () => {
    expect(formatBytes(MB)).toBe('1.0MB')
    expect(formatBytes(3 * MB)).toBe('3.0MB')
    expect(formatBytes(1.25 * MB)).toBe('1.3MB')
  })

  it('GB 档（漏 GB 的实现会把 500MB 显示成 512000.0MB）', () => {
    expect(formatBytes(GB)).toBe('1.0GB')
    expect(formatBytes(500 * MB)).toBe('500.0MB')
    expect(formatBytes(2.5 * GB)).toBe('2.5GB')
    expect(formatBytes(5 * GB)).toBe('5.0GB')
  })

  it('四舍五入满 1024 时升档，不出现「1024B / 1024KB」这种数', () => {
    // 1023.6B 按 B 取整 → 1024，此时应升到 KB 档而不是显示「1024B」
    expect(formatBytes(1023.6)).toBe('1KB')
    // 1023.6KB 按 KB 取整 → 1024，升到 MB 档保留一位
    expect(formatBytes(1023.6 * KB)).toBe('1.0MB')
  })

  it('space 选项在数字与单位间留一个空格（文件夹列表口径）', () => {
    expect(formatBytes(0, { space: true })).toBe('0 B')
    expect(formatBytes(999, { space: true })).toBe('999 B')
    expect(formatBytes(KB, { space: true })).toBe('1 KB')
    expect(formatBytes(3 * MB, { space: true })).toBe('3.0 MB')
    expect(formatBytes(2 * GB, { space: true })).toBe('2.0 GB')
  })

  it('decimals 覆盖各档默认小数位', () => {
    expect(formatBytes(1.5 * MB, { decimals: 0 })).toBe('2MB')
    expect(formatBytes(1.234 * GB, { decimals: 2 })).toBe('1.23GB')
    expect(formatBytes(512 * KB, { decimals: 1 })).toBe('512.0KB')
  })
})
