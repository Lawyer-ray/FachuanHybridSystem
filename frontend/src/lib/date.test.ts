/**
 * lib/date 纯逻辑单测（node 环境）。
 * 覆盖自 home/domain（pad2/dateKey/todayKey）、workbench/domain（todayStr）
 * 与 document-recognition/domain（toLocalInputValue）收敛来的全部用法。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { dateKey, pad2, toLocalInputValue, todayKey } from './date'

describe('pad2', () => {
  it('补零：3 → 03，12 → 12', () => {
    expect(pad2(3)).toBe('03')
    expect(pad2(12)).toBe('12')
  })
})

describe('dateKey', () => {
  it('用本地时区，不会因 UTC 差一天（东八区凌晨 00:30 不退到前一天）', () => {
    // 2026-09-17 00:30 本地时间（东八区）若按 toISOString 会变成 09-16
    const d = new Date(2026, 8, 17, 0, 30)
    expect(dateKey(d)).toBe('2026-09-17')
  })

  it('月/日两位补零（原 workbench todayStr 口径）', () => {
    expect(dateKey(new Date(2026, 0, 9))).toBe('2026-01-09')
    expect(dateKey(new Date(2026, 11, 31))).toBe('2026-12-31')
  })
})

describe('todayKey', () => {
  it('默认取当前时刻的本地 dateKey', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 9, 1, 8, 0, 0))
    expect(todayKey()).toBe('2026-10-01')
    vi.useRealTimers()
  })

  it('显式传入 now 时按传入值计算', () => {
    expect(todayKey(new Date(2026, 1, 3))).toBe('2026-02-03')
  })
})

describe('toLocalInputValue', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('带时区偏移的 ISO 转成本地 datetime-local 值', () => {
    // UTC 01:30 = 北京 09:30（测试机时区无关：用显式偏移表达「这一刻」）
    const local = toLocalInputValue('2026-10-15T01:30:00+00:00')
    expect(local).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/)
    expect(local).toHaveLength(16)
  })

  it('naive ISO 原样保留日期时间（parseISO 按本地解析，不偏移）', () => {
    expect(toLocalInputValue('2026-10-15T09:30')).toBe('2026-10-15T09:30')
  })

  it('date-only 串按本地零点，不被误按 UTC 解析偏一天', () => {
    expect(toLocalInputValue('2026-10-15')).toBe('2026-10-15T00:00')
  })

  it('空值与非法输入返回空串', () => {
    expect(toLocalInputValue(null)).toBe('')
    expect(toLocalInputValue(undefined)).toBe('')
    expect(toLocalInputValue('')).toBe('')
    expect(toLocalInputValue('not-a-date')).toBe('')
  })

  it('补零：个位月/日/时/分都两位', () => {
    expect(toLocalInputValue('2026-01-02T03:04')).toBe('2026-01-02T03:04')
  })
})
