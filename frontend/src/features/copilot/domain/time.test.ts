import { describe, expect, it } from 'vitest'

import { formatClock } from './time'

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
