/**
 * LPR Utils Tests
 * 测试 LPR 计算工具函数
 */

import {
  RATE_MODE_OPTIONS,
  RATE_TYPE_OPTIONS,
  YEAR_DAYS_OPTIONS,
  DATE_INCLUSION_OPTIONS,
  CUSTOM_RATE_UNIT_OPTIONS,
  formatMoney,
  formatDate,
  getRateInfo,
  groupByPrincipal,
  formatRateDisplay,
} from '../lpr'
import type { CalculationPeriod } from '../../api'

describe('lpr utils constants', () => {
  it('RATE_MODE_OPTIONS has 3 options', () => {
    expect(RATE_MODE_OPTIONS).toHaveLength(3)
    expect(RATE_MODE_OPTIONS.map((o) => o.value)).toEqual(['lpr', 'custom', 'delay'])
  })

  it('RATE_TYPE_OPTIONS has 2 options', () => {
    expect(RATE_TYPE_OPTIONS).toHaveLength(2)
  })

  it('YEAR_DAYS_OPTIONS has 3 options', () => {
    expect(YEAR_DAYS_OPTIONS).toHaveLength(3)
    expect(YEAR_DAYS_OPTIONS.map((o) => o.value)).toEqual([360, 365, 0])
  })

  it('DATE_INCLUSION_OPTIONS has 4 options', () => {
    expect(DATE_INCLUSION_OPTIONS).toHaveLength(4)
  })

  it('CUSTOM_RATE_UNIT_OPTIONS has 3 options', () => {
    expect(CUSTOM_RATE_UNIT_OPTIONS).toHaveLength(3)
  })
})

describe('formatMoney', () => {
  it('formats a valid number string', () => {
    const result = formatMoney('12345.67')
    expect(result).toContain('12')
    expect(result).toContain('345')
    expect(result).toContain('67')
  })

  it('returns 0.00 for null/undefined/empty', () => {
    expect(formatMoney(null)).toBe('0.00')
    expect(formatMoney(undefined)).toBe('0.00')
    expect(formatMoney('')).toBe('0.00')
  })

  it('returns raw value for non-numeric string', () => {
    expect(formatMoney('abc')).toBe('abc')
  })

  it('formats integer value with decimals', () => {
    const result = formatMoney('1000')
    expect(result).toContain('1')
    expect(result).toContain('000')
    expect(result).toContain('00')
  })
})

describe('formatDate', () => {
  it('strips time portion from ISO date', () => {
    expect(formatDate('2026-01-15T10:30:00Z')).toBe('2026-01-15')
  })

  it('returns date as-is if no T', () => {
    expect(formatDate('2026-01-15')).toBe('2026-01-15')
  })

  it('returns empty for empty string', () => {
    expect(formatDate('')).toBe('')
  })
})

describe('getRateInfo', () => {
  const baseForm = {
    start_date: '',
    end_date: '',
    principal: '',
    rate_mode: '',
    rate_type: '1y',
    multiplier: '1.0',
    custom_rate_unit: 'percent',
    custom_rate_value: '3.85',
    year_days: 365,
    date_inclusion: 'both',
    changes: [],
  }

  it('returns LPR info for lpr mode with 1y type', () => {
    expect(getRateInfo({ ...baseForm, rate_mode: 'lpr', rate_type: '1y', multiplier: '1.3' })).toBe('LPR 一年期 · 1.3倍')
  })

  it('returns LPR info for lpr mode with 5y type', () => {
    expect(getRateInfo({ ...baseForm, rate_mode: 'lpr', rate_type: '5y', multiplier: '1.0' })).toBe('LPR 五年期 · 1.0倍')
  })

  it('returns delay info for delay mode', () => {
    expect(getRateInfo({ ...baseForm, rate_mode: 'delay' })).toBe('迟延履行 · 1.75‱/天')
  })

  it('returns custom info for percent unit', () => {
    expect(getRateInfo({ ...baseForm, rate_mode: 'custom', custom_rate_value: '5.5', custom_rate_unit: 'percent' })).toBe('自定义 · 5.5%/年')
  })

  it('returns custom info for permille unit', () => {
    expect(getRateInfo({ ...baseForm, rate_mode: 'custom', custom_rate_value: '1.0', custom_rate_unit: 'permille' })).toBe('自定义 · 1.0‰/天')
  })

  it('returns custom info for permyriad unit', () => {
    expect(getRateInfo({ ...baseForm, rate_mode: 'custom', custom_rate_value: '1.75', custom_rate_unit: 'permyriad' })).toBe('自定义 · 1.75‱/天')
  })
})

describe('groupByPrincipal', () => {
  it('groups periods with same principal and contiguous dates', () => {
    const periods: CalculationPeriod[] = [
      { id: 1, principal: '100000', start_date: '2024-01-01', end_date: '2024-06-30', days: 181, rate: '3.85', interest: '1925.00', rate_mode: 'lpr' },
      { id: 2, principal: '100000', start_date: '2024-07-01', end_date: '2024-12-31', days: 183, rate: '3.85', interest: '1945.00', rate_mode: 'lpr' },
    ]
    const groups = groupByPrincipal(periods)
    expect(groups).toHaveLength(1)
    expect(groups[0].principal).toBe(100000)
    expect(groups[0].periods).toHaveLength(2)
    expect(groups[0].totalDays).toBe(364)
  })

  it('creates separate groups for different principals', () => {
    const periods: CalculationPeriod[] = [
      { id: 1, principal: '100000', start_date: '2024-01-01', end_date: '2024-06-30', days: 181, rate: '3.85', interest: '1925.00', rate_mode: 'lpr' },
      { id: 2, principal: '200000', start_date: '2024-07-01', end_date: '2024-12-31', days: 183, rate: '3.85', interest: '3890.00', rate_mode: 'lpr' },
    ]
    const groups = groupByPrincipal(periods)
    expect(groups).toHaveLength(2)
  })

  it('handles empty periods array', () => {
    expect(groupByPrincipal([])).toEqual([])
  })

  it('handles single period', () => {
    const periods: CalculationPeriod[] = [
      { id: 1, principal: '50000', start_date: '2024-01-01', end_date: '2024-06-30', days: 181, rate: '3.85', interest: '962.50', rate_mode: 'lpr' },
    ]
    const groups = groupByPrincipal(periods)
    expect(groups).toHaveLength(1)
    expect(groups[0].totalInterest).toBeCloseTo(962.5)
  })
})

describe('formatRateDisplay', () => {
  it('formats LPR rate', () => {
    expect(formatRateDisplay('3.85', null, 'lpr')).toBe('3.85%/年')
  })

  it('formats permille rate', () => {
    expect(formatRateDisplay('1.0', 'permille', 'custom')).toBe('1.00‰/天')
  })

  it('formats permyriad rate', () => {
    expect(formatRateDisplay('1.75', 'permyriad', 'custom')).toBe('1.75‱/天')
  })

  it('formats percent rate as default', () => {
    expect(formatRateDisplay('5.5', 'percent', 'custom')).toBe('5.50%/年')
  })

  it('handles zero rate', () => {
    expect(formatRateDisplay('0', null, 'lpr')).toBe('0.00%/年')
  })

  it('handles non-numeric rate', () => {
    expect(formatRateDisplay('abc', null, 'lpr')).toBe('0.00%/年')
  })
})
