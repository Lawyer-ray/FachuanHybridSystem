import { formatDate, formatDateOnly, formatRelativeTime, formatShortDate } from '../date'

describe('formatDate', () => {
  it('returns "-" for null', () => {
    expect(formatDate(null)).toBe('-')
  })

  it('returns "-" for undefined', () => {
    expect(formatDate(undefined)).toBe('-')
  })

  it('returns "-" for empty string', () => {
    expect(formatDate('')).toBe('-')
  })

  it('formats a valid ISO date string', () => {
    const result = formatDate('2025-06-15T10:30:00Z')
    // Should contain date parts
    expect(result).toContain('2025')
    expect(result).not.toBe('-')
  })

  it('handles invalid date string gracefully', () => {
    const result = formatDate('not-a-date')
    // new Date('not-a-date') is Invalid Date; toLocaleString returns "Invalid Date"
    expect(result).toBeTruthy()
  })
})

describe('formatDateOnly', () => {
  it('returns "-" for null', () => {
    expect(formatDateOnly(null)).toBe('-')
  })

  it('returns "-" for undefined', () => {
    expect(formatDateOnly(undefined)).toBe('-')
  })

  it('formats a valid ISO date string', () => {
    const result = formatDateOnly('2025-06-15T10:30:00Z')
    expect(result).toContain('2025')
    expect(result).not.toBe('-')
  })

  it('handles invalid date string gracefully', () => {
    const result = formatDateOnly('bad')
    expect(result).toBeTruthy()
  })
})

describe('formatRelativeTime', () => {
  it('returns "-" for null', () => {
    expect(formatRelativeTime(null)).toBe('-')
  })

  it('returns "-" for undefined', () => {
    expect(formatRelativeTime(undefined)).toBe('-')
  })

  it('formats a date from this year (not today) with month-day time', () => {
    // Use a date that is in the current year but not today
    const now = new Date()
    const thisYear = now.getFullYear()
    // Use Jan 1 of this year
    const iso = `${thisYear}-01-01T08:30:00Z`
    const result = formatRelativeTime(iso)
    expect(result).not.toBe('-')
    // Should contain month/day separator
    expect(result).toContain('01')
  })

  it('formats today date with time only', () => {
    // Create a date string for "today" - use the current date
    const now = new Date()
    const year = now.getFullYear()
    const month = String(now.getMonth() + 1).padStart(2, '0')
    const day = String(now.getDate()).padStart(2, '0')
    const iso = `${year}-${month}-${day}T14:30:00Z`
    const result = formatRelativeTime(iso)
    expect(result).not.toBe('-')
    // Should be a time format (contains colon)
    expect(result).toContain(':')
  })

  it('formats a cross-year date with full date', () => {
    const result = formatRelativeTime('2020-03-15T10:00:00Z')
    expect(result).not.toBe('-')
    expect(result).toContain('2020')
  })

  it('handles invalid date string gracefully', () => {
    const result = formatRelativeTime('invalid')
    expect(result).toBeTruthy()
  })
})

describe('formatShortDate', () => {
  it('returns "-" for null', () => {
    expect(formatShortDate(null)).toBe('-')
  })

  it('returns "-" for undefined', () => {
    expect(formatShortDate(undefined)).toBe('-')
  })

  it('formats a valid date', () => {
    const result = formatShortDate('2025-06-15T10:30:00Z')
    expect(result).not.toBe('-')
    expect(result).toContain('06')
    expect(result).toContain('15')
  })

  it('handles invalid date string gracefully', () => {
    const result = formatShortDate('garbage')
    expect(result).toBeTruthy()
  })
})
