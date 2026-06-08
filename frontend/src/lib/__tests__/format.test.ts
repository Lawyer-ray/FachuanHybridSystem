import { formatCurrency, formatAmount, formatAmountInt } from '../format'

describe('formatCurrency', () => {
  it('formats number with 2 decimal places', () => {
    const result = formatCurrency(12345.6)
    expect(result).toContain('12')
    expect(result).toContain('345')
    expect(result).toContain('60')
  })

  it('handles zero', () => {
    const result = formatCurrency(0)
    expect(result).toContain('0')
  })

  it('handles negative numbers', () => {
    const result = formatCurrency(-100.5)
    expect(result).toContain('100')
    expect(result).toContain('50')
  })

  it('formats integer with trailing zeros', () => {
    const result = formatCurrency(100)
    expect(result).toContain('100')
    expect(result).toContain('00')
  })
})

describe('formatAmount', () => {
  it('returns em-dash for null', () => {
    expect(formatAmount(null)).toBe('—')
  })

  it('returns em-dash for undefined', () => {
    expect(formatAmount(undefined)).toBe('—')
  })

  it('formats amount with yen prefix', () => {
    const result = formatAmount(1234.56)
    expect(result).toContain('¥')
    expect(result).toContain('1')
    expect(result).toContain('234')
    expect(result).toContain('56')
  })

  it('formats zero amount', () => {
    const result = formatAmount(0)
    expect(result).toContain('¥')
    expect(result).toContain('0')
  })
})

describe('formatAmountInt', () => {
  it('returns em-dash for null', () => {
    expect(formatAmountInt(null)).toBe('—')
  })

  it('returns em-dash for undefined', () => {
    expect(formatAmountInt(undefined)).toBe('—')
  })

  it('formats integer amount with yen prefix', () => {
    const result = formatAmountInt(12345)
    expect(result).toContain('¥')
    expect(result).toContain('12')
    expect(result).toContain('345')
  })

  it('formats zero', () => {
    const result = formatAmountInt(0)
    expect(result).toContain('¥')
    expect(result).toContain('0')
  })
})
