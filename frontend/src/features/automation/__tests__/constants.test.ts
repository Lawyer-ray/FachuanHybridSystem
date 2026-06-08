/**
 * Automation Constants Tests
 * 测试轮询间隔和文件上传配置
 */

import { POLLING_INTERVALS, FILE_UPLOAD, ACCEPTED_FILE_TYPES, MAX_FILE_SIZE } from '../constants'

describe('POLLING_INTERVALS', () => {
  it('defines QUOTE_RUNNING as 3000ms', () => {
    expect(POLLING_INTERVALS.QUOTE_RUNNING).toBe(3000)
  })

  it('defines RECOGNITION_PROCESSING as 2000ms', () => {
    expect(POLLING_INTERVALS.RECOGNITION_PROCESSING).toBe(2000)
  })

  it('defines POLLING_TIMEOUT as 5 minutes', () => {
    expect(POLLING_INTERVALS.POLLING_TIMEOUT).toBe(300000)
  })
})

describe('FILE_UPLOAD', () => {
  it('defines ACCEPTED_FILE_TYPES with PDF, JPEG, PNG', () => {
    expect(FILE_UPLOAD.ACCEPTED_FILE_TYPES).toContain('application/pdf')
    expect(FILE_UPLOAD.ACCEPTED_FILE_TYPES).toContain('image/jpeg')
    expect(FILE_UPLOAD.ACCEPTED_FILE_TYPES).toContain('image/png')
    expect(FILE_UPLOAD.ACCEPTED_FILE_TYPES).toHaveLength(3)
  })

  it('defines MAX_FILE_SIZE as 10MB', () => {
    expect(FILE_UPLOAD.MAX_FILE_SIZE).toBe(10 * 1024 * 1024)
  })
})

describe('convenience exports', () => {
  it('ACCEPTED_FILE_TYPES re-exports from FILE_UPLOAD', () => {
    expect(ACCEPTED_FILE_TYPES).toBe(FILE_UPLOAD.ACCEPTED_FILE_TYPES)
  })

  it('MAX_FILE_SIZE re-exports from FILE_UPLOAD', () => {
    expect(MAX_FILE_SIZE).toBe(FILE_UPLOAD.MAX_FILE_SIZE)
  })
})
