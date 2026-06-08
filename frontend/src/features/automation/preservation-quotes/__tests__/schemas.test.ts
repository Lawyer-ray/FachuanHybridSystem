/**
 * Preservation Quotes Schemas Tests
 * 测试创建询价表单验证
 */

import { quoteCreateSchema } from '../schemas'

describe('quoteCreateSchema', () => {
  const validData = {
    preserve_amount: 100000,
    corp_id: 'corp-001',
    category_id: 'cat-001',
    credential_id: 1,
  }

  it('accepts valid data', () => {
    const result = quoteCreateSchema.safeParse(validData)
    expect(result.success).toBe(true)
  })

  it('rejects missing preserve_amount', () => {
    const { preserve_amount, ...rest } = validData
    const result = quoteCreateSchema.safeParse(rest)
    expect(result.success).toBe(false)
  })

  it('rejects zero preserve_amount', () => {
    const result = quoteCreateSchema.safeParse({ ...validData, preserve_amount: 0 })
    expect(result.success).toBe(false)
  })

  it('rejects negative preserve_amount', () => {
    const result = quoteCreateSchema.safeParse({ ...validData, preserve_amount: -100 })
    expect(result.success).toBe(false)
  })

  it('rejects missing corp_id', () => {
    const { corp_id, ...rest } = validData
    const result = quoteCreateSchema.safeParse(rest)
    expect(result.success).toBe(false)
  })

  it('rejects empty corp_id', () => {
    const result = quoteCreateSchema.safeParse({ ...validData, corp_id: '' })
    expect(result.success).toBe(false)
  })

  it('rejects missing category_id', () => {
    const { category_id, ...rest } = validData
    const result = quoteCreateSchema.safeParse(rest)
    expect(result.success).toBe(false)
  })

  it('rejects empty category_id', () => {
    const result = quoteCreateSchema.safeParse({ ...validData, category_id: '' })
    expect(result.success).toBe(false)
  })

  it('rejects missing credential_id', () => {
    const { credential_id, ...rest } = validData
    const result = quoteCreateSchema.safeParse(rest)
    expect(result.success).toBe(false)
  })

  it('rejects zero credential_id', () => {
    const result = quoteCreateSchema.safeParse({ ...validData, credential_id: 0 })
    expect(result.success).toBe(false)
  })

  it('rejects non-integer credential_id', () => {
    const result = quoteCreateSchema.safeParse({ ...validData, credential_id: 1.5 })
    expect(result.success).toBe(false)
  })

  it('rejects negative credential_id', () => {
    const result = quoteCreateSchema.safeParse({ ...validData, credential_id: -1 })
    expect(result.success).toBe(false)
  })
})
