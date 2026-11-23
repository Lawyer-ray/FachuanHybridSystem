import { describe, expect, it } from 'vitest'

import { formatClock, formatSessionStamp } from './time'

describe('formatClock', () => {
  it('补零到 HH:mm', () => {
    const at = new Date(2026, 10, 20, 9, 5, 30).getTime()
    expect(formatClock(at)).toBe('09:05')
  })

  it('下午按 24 小时制', () => {
    const at = new Date(2026, 10, 20, 21, 40).getTime()
    expect(formatClock(at)).toBe('21:40')
  })

  it('无值/非法值返回空串（调用方不渲染）', () => {
    expect(formatClock(undefined)).toBe('')
    expect(formatClock(null)).toBe('')
    expect(formatClock(0)).toBe('')
    expect(formatClock(Number.NaN)).toBe('')
  })
})

describe('formatSessionStamp', () => {
  it('ISO → MM-DD HH:MM', () => {
    expect(formatSessionStamp('2026-10-20T10:00:00')).toBe('10-20 10:00')
  })

  it('带时区偏移与毫秒不错位（偏移在第 19 位之后）', () => {
    expect(formatSessionStamp('2026-11-20T09:05:30.123+08:00')).toBe('11-20 09:05')
    expect(formatSessionStamp('2026-11-20T09:05:30.123Z')).toBe('11-20 09:05')
  })

  it('不做本地时区换算：输出即服务端记下的那一刻', () => {
    // 走 Date 会在 UTC 机器上得到另一个 HH:mm（这里锁死「不过 Date」的口径）
    expect(formatSessionStamp('2026-11-20T23:59:00+00:00')).toBe('11-20 23:59')
  })
})
