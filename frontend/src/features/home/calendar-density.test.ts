import { describe, expect, it } from 'vitest'

import { COMPACT_BELOW, MEDIUM_BELOW, densityForWidth, maxRowsForWidth } from './calendar-density'

describe('densityForWidth', () => {
  it('未量到宽（0 / NaN / 负数）时用兜底档', () => {
    expect(densityForWidth(0, 'wide')).toBe('wide')
    expect(densityForWidth(0, 'compact')).toBe('compact')
    expect(densityForWidth(Number.NaN, 'medium')).toBe('medium')
    expect(densityForWidth(-1, 'wide')).toBe('wide')
  })

  it('窄面板 → compact（AI 助手并排 / 分屏压窄后仍能读）', () => {
    expect(densityForWidth(332, 'wide')).toBe('compact')
    expect(densityForWidth(COMPACT_BELOW - 1, 'wide')).toBe('compact')
  })

  it('中宽面板 → medium', () => {
    expect(densityForWidth(COMPACT_BELOW, 'wide')).toBe('medium')
    expect(densityForWidth(836, 'wide')).toBe('medium')
    expect(densityForWidth(MEDIUM_BELOW - 1, 'wide')).toBe('medium')
  })

  it('宽面板 → wide（五行卡片）', () => {
    expect(densityForWidth(MEDIUM_BELOW, 'compact')).toBe('wide')
    expect(densityForWidth(1600, 'compact')).toBe('wide')
  })
})

describe('maxRowsForWidth', () => {
  it('按面板净宽分三档，量不到宽时给 3（不会把格子撑爆）', () => {
    expect(maxRowsForWidth(0)).toBe(3)
    expect(maxRowsForWidth(1200)).toBe(4)
    expect(maxRowsForWidth(1900)).toBe(5)
  })
})
