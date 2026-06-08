import { MAX_FILE_SIZE_5MB, MAX_FILE_SIZE_10MB, isPdf, formatFileSize } from '../file-utils'

describe('constants', () => {
  it('MAX_FILE_SIZE_5MB is 5MB', () => {
    expect(MAX_FILE_SIZE_5MB).toBe(5 * 1024 * 1024)
  })

  it('MAX_FILE_SIZE_10MB is 10MB', () => {
    expect(MAX_FILE_SIZE_10MB).toBe(10 * 1024 * 1024)
  })
})

describe('isPdf', () => {
  it('returns true for PDF files', () => {
    const file = new File([''], 'test.pdf', { type: 'application/pdf' })
    expect(isPdf(file)).toBe(true)
  })

  it('returns false for non-PDF files', () => {
    const file = new File([''], 'test.txt', { type: 'text/plain' })
    expect(isPdf(file)).toBe(false)
  })

  it('returns false for empty type', () => {
    const file = new File([''], 'test', { type: '' })
    expect(isPdf(file)).toBe(false)
  })
})

describe('formatFileSize', () => {
  it('formats bytes', () => {
    expect(formatFileSize(500)).toBe('500 B')
  })

  it('formats kilobytes', () => {
    expect(formatFileSize(1024)).toBe('1.0 KB')
  })

  it('formats megabytes', () => {
    expect(formatFileSize(1024 * 1024)).toBe('1.0 MB')
  })

  it('formats zero bytes', () => {
    expect(formatFileSize(0)).toBe('0 B')
  })

  it('formats fractional KB', () => {
    expect(formatFileSize(1536)).toBe('1.5 KB')
  })
})
