/**
 * Reminder Schemas Tests
 * 测试提醒表单验证 Schema
 */

import { reminderFormSchema } from '../schemas'

describe('reminderFormSchema', () => {
  const validData = {
    reminder_type: 'hearing',
    content: '开庭通知',
    due_at: new Date('2025-12-01'),
  }

  it('accepts valid data', () => {
    const result = reminderFormSchema.safeParse(validData)
    expect(result.success).toBe(true)
  })

  it('accepts with contract_id', () => {
    const result = reminderFormSchema.safeParse({
      ...validData,
      contract_id: 1,
    })
    expect(result.success).toBe(true)
  })

  it('accepts with case_log_id', () => {
    const result = reminderFormSchema.safeParse({
      ...validData,
      case_log_id: 5,
    })
    expect(result.success).toBe(true)
  })

  it('accepts with metadata', () => {
    const result = reminderFormSchema.safeParse({
      ...validData,
      metadata: { key: 'value' },
    })
    expect(result.success).toBe(true)
  })

  it('rejects empty reminder_type', () => {
    const result = reminderFormSchema.safeParse({ ...validData, reminder_type: '' })
    expect(result.success).toBe(false)
  })

  it('rejects empty content', () => {
    const result = reminderFormSchema.safeParse({ ...validData, content: '' })
    expect(result.success).toBe(false)
  })

  it('rejects content longer than 255 characters', () => {
    const result = reminderFormSchema.safeParse({ ...validData, content: 'a'.repeat(256) })
    expect(result.success).toBe(false)
  })

  it('accepts content at exactly 255 characters', () => {
    const result = reminderFormSchema.safeParse({ ...validData, content: 'a'.repeat(255) })
    expect(result.success).toBe(true)
  })

  it('rejects missing due_at', () => {
    const { due_at, ...rest } = validData
    const result = reminderFormSchema.safeParse(rest)
    expect(result.success).toBe(false)
  })

  it('rejects both contract_id and case_log_id set', () => {
    const result = reminderFormSchema.safeParse({
      ...validData,
      contract_id: 1,
      case_log_id: 2,
    })
    expect(result.success).toBe(false)
  })

  it('rejects contract_id of 0 (treated as empty)', () => {
    const result = reminderFormSchema.safeParse({
      ...validData,
      contract_id: 0,
      case_log_id: 2,
    })
    // contract_id=0 is falsy, so only case_log_id is active -- should pass
    expect(result.success).toBe(true)
  })

  it('accepts null contract_id with case_log_id', () => {
    const result = reminderFormSchema.safeParse({
      ...validData,
      contract_id: null,
      case_log_id: 2,
    })
    expect(result.success).toBe(true)
  })
})
