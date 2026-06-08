/**
 * Auth Schemas Tests
 * 测试 loginSchema 和 registerSchema 的验证逻辑
 */

import { loginSchema, registerSchema } from '../schemas'

describe('loginSchema', () => {
  it('accepts valid credentials', () => {
    const result = loginSchema.safeParse({ username: 'admin', password: 'secret123' })
    expect(result.success).toBe(true)
  })

  it('rejects empty username', () => {
    const result = loginSchema.safeParse({ username: '', password: 'secret123' })
    expect(result.success).toBe(false)
  })

  it('rejects empty password', () => {
    const result = loginSchema.safeParse({ username: 'admin', password: '' })
    expect(result.success).toBe(false)
  })

  it('rejects missing fields', () => {
    const result = loginSchema.safeParse({})
    expect(result.success).toBe(false)
  })
})

describe('registerSchema', () => {
  const validData = {
    username: 'test_user',
    password: 'password123',
    confirmPassword: 'password123',
  }

  it('accepts valid registration data', () => {
    const result = registerSchema.safeParse(validData)
    expect(result.success).toBe(true)
  })

  it('accepts with optional fields', () => {
    const result = registerSchema.safeParse({
      ...validData,
      real_name: '张三',
      phone: '15912345678', // allowlist secret: test fixture for schema validation
    })
    expect(result.success).toBe(true)
  })

  it('accepts empty optional fields', () => {
    const result = registerSchema.safeParse({
      ...validData,
      real_name: '',
      phone: '',
    })
    expect(result.success).toBe(true)
  })

  it('rejects username shorter than 3 characters', () => {
    const result = registerSchema.safeParse({ ...validData, username: 'ab' })
    expect(result.success).toBe(false)
  })

  it('rejects username longer than 20 characters', () => {
    const result = registerSchema.safeParse({ ...validData, username: 'a'.repeat(21) })
    expect(result.success).toBe(false)
  })

  it('rejects username with special characters', () => {
    const result = registerSchema.safeParse({ ...validData, username: 'user@name' })
    expect(result.success).toBe(false)
  })

  it('accepts username with underscores', () => {
    const result = registerSchema.safeParse({ ...validData, username: 'user_name_123' })
    expect(result.success).toBe(true)
  })

  it('rejects password shorter than 6 characters', () => {
    const result = registerSchema.safeParse({ ...validData, password: '12345', confirmPassword: '12345' })
    expect(result.success).toBe(false)
  })

  it('rejects password longer than 32 characters', () => {
    const longPw = 'a'.repeat(33)
    const result = registerSchema.safeParse({ ...validData, password: longPw, confirmPassword: longPw })
    expect(result.success).toBe(false)
  })

  it('rejects mismatched passwords', () => {
    const result = registerSchema.safeParse({
      ...validData,
      confirmPassword: 'different_password',
    })
    expect(result.success).toBe(false)
  })

  it('rejects invalid phone number', () => {
    const result = registerSchema.safeParse({ ...validData, phone: '12345' })
    expect(result.success).toBe(false)
  })

  it('accepts valid Chinese mobile number', () => {
    const result = registerSchema.safeParse({ ...validData, phone: '15912345678' }) // allowlist secret: test fixture
    expect(result.success).toBe(true)
  })
})
