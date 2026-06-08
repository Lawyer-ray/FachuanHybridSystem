/**
 * Document Recognition Schemas Tests
 * 测试手动绑定和文件验证逻辑
 */

import { manualBindingSchema, updateRecognitionInfoSchema, fileValidation, FILE_ERRORS } from '../schemas'

describe('manualBindingSchema', () => {
  it('accepts valid binding data', () => {
    const result = manualBindingSchema.safeParse({ case_id: 1 })
    expect(result.success).toBe(true)
  })

  it('accepts with optional fields', () => {
    const result = manualBindingSchema.safeParse({
      case_id: 42,
      document_type: '判决书',
      key_time: '2025-01-01',
    })
    expect(result.success).toBe(true)
  })

  it('rejects missing case_id', () => {
    const result = manualBindingSchema.safeParse({})
    expect(result.success).toBe(false)
  })

  it('rejects zero case_id', () => {
    const result = manualBindingSchema.safeParse({ case_id: 0 })
    expect(result.success).toBe(false)
  })

  it('rejects negative case_id', () => {
    const result = manualBindingSchema.safeParse({ case_id: -1 })
    expect(result.success).toBe(false)
  })

  it('rejects non-integer case_id', () => {
    const result = manualBindingSchema.safeParse({ case_id: 1.5 })
    expect(result.success).toBe(false)
  })

  it('rejects non-number case_id', () => {
    const result = manualBindingSchema.safeParse({ case_id: 'abc' })
    expect(result.success).toBe(false)
  })
})

describe('updateRecognitionInfoSchema', () => {
  it('accepts empty object (all optional)', () => {
    const result = updateRecognitionInfoSchema.safeParse({})
    expect(result.success).toBe(true)
  })

  it('accepts with document_type', () => {
    const result = updateRecognitionInfoSchema.safeParse({ document_type: '调解书' })
    expect(result.success).toBe(true)
  })

  it('accepts with key_time', () => {
    const result = updateRecognitionInfoSchema.safeParse({ key_time: '2025-06-01' })
    expect(result.success).toBe(true)
  })
})

describe('fileValidation', () => {
  function createMockFile(type: string, size: number): File {
    const buffer = new ArrayBuffer(size)
    return new File([buffer], 'test-file', { type })
  }

  describe('isValidType', () => {
    it('accepts PDF files', () => {
      const file = createMockFile('application/pdf', 1024)
      expect(fileValidation.isValidType(file)).toBe(true)
    })

    it('accepts JPEG images', () => {
      const file = createMockFile('image/jpeg', 1024)
      expect(fileValidation.isValidType(file)).toBe(true)
    })

    it('accepts PNG images', () => {
      const file = createMockFile('image/png', 1024)
      expect(fileValidation.isValidType(file)).toBe(true)
    })

    it('rejects text files', () => {
      const file = createMockFile('text/plain', 1024)
      expect(fileValidation.isValidType(file)).toBe(false)
    })

    it('rejects Word documents', () => {
      const file = createMockFile('application/msword', 1024)
      expect(fileValidation.isValidType(file)).toBe(false)
    })
  })

  describe('isValidSize', () => {
    it('accepts file under 10MB', () => {
      const file = createMockFile('application/pdf', 5 * 1024 * 1024)
      expect(fileValidation.isValidSize(file)).toBe(true)
    })

    it('accepts file exactly 10MB', () => {
      const file = createMockFile('application/pdf', 10 * 1024 * 1024)
      expect(fileValidation.isValidSize(file)).toBe(true)
    })

    it('rejects file over 10MB', () => {
      const file = createMockFile('application/pdf', 11 * 1024 * 1024)
      expect(fileValidation.isValidSize(file)).toBe(false)
    })
  })

  describe('validate', () => {
    it('returns valid for accepted PDF under size limit', () => {
      const file = createMockFile('application/pdf', 1024)
      const result = fileValidation.validate(file)
      expect(result.valid).toBe(true)
      expect(result.error).toBeUndefined()
    })

    it('returns error for invalid type', () => {
      const file = createMockFile('text/plain', 1024)
      const result = fileValidation.validate(file)
      expect(result.valid).toBe(false)
      expect(result.error).toContain('不支持的文件格式')
    })

    it('returns error for file too large', () => {
      const file = createMockFile('application/pdf', 11 * 1024 * 1024)
      const result = fileValidation.validate(file)
      expect(result.valid).toBe(false)
      expect(result.error).toContain('10MB')
    })

    it('checks type before size', () => {
      const file = createMockFile('text/plain', 11 * 1024 * 1024)
      const result = fileValidation.validate(file)
      expect(result.valid).toBe(false)
      expect(result.error).toContain('不支持的文件格式')
    })
  })
})

describe('FILE_ERRORS', () => {
  it('defines all error messages', () => {
    expect(FILE_ERRORS.INVALID_TYPE).toBeTruthy()
    expect(FILE_ERRORS.FILE_TOO_LARGE).toBeTruthy()
    expect(FILE_ERRORS.UPLOAD_FAILED).toBeTruthy()
    expect(FILE_ERRORS.NETWORK_ERROR).toBeTruthy()
  })

  it('has exactly 4 error messages', () => {
    expect(Object.keys(FILE_ERRORS)).toHaveLength(4)
  })
})
