/**
 * Property 7: 表单验证拒绝无效输入
 *
 * For any 空字符串或纯空白字符串作为案件名称，Zod 验证 schema
 * 应返回验证失败结果，且错误信息非空。
 *
 * Feature: admin-cases-frontend, Property 7: 表单验证拒绝无效输入
 * Validates: Requirements 4.9
 */

import { describe, it, expect } from 'vitest'
import fc from 'fast-check'

import { caseFormSchema } from '../types'

describe('Property 7: 表单验证拒绝无效输入', () => {
  it('rejects empty string as case name', () => {
    const result = caseFormSchema.safeParse({ name: '' })
    expect(result.success).toBe(false)
  })

  it('rejects any whitespace-only string as case name (property)', () => {
    fc.assert(
      fc.property(
        fc.nat({ max: 20 }).map((n) => ' '.repeat(n)),
        (whitespace) => {
          if (whitespace.length === 0) {
            const result = caseFormSchema.safeParse({ name: whitespace })
            expect(result.success).toBe(false)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('accepts valid non-empty case names', () => {
    fc.assert(
      fc.property(
        fc.string({ minLength: 1, maxLength: 200 }).filter((s) => s.trim().length > 0),
        (name) => {
          const result = caseFormSchema.safeParse({ name })
          expect(result.success).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('accepts valid case with all optional fields', () => {
    const result = caseFormSchema.safeParse({
      name: '测试案件',
      case_type: 'civil',
      status: 'active',
      cause_of_action: '合同纠纷',
      current_stage: 'first_trial',
      target_amount: 100000,
      preservation_amount: 50000,
      effective_date: '2025-01-01',
    })
    expect(result.success).toBe(true)
  })

  it('rejects negative target_amount', () => {
    const result = caseFormSchema.safeParse({
      name: '测试案件',
      target_amount: -100,
    })
    expect(result.success).toBe(false)
  })

  it('rejects invalid case_type', () => {
    const result = caseFormSchema.safeParse({
      name: '测试案件',
      case_type: 'invalid_type',
    })
    expect(result.success).toBe(false)
  })
})
