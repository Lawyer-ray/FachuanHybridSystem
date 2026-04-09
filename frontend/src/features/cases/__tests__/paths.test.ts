/**
 * Property 5: 路径生成函数正确性
 *
 * For any 案件 ID 字符串，generatePath.caseDetail(id) 应返回 /admin/cases/${id}，
 * generatePath.caseEdit(id) 应返回 /admin/cases/${id}/edit。
 *
 * Feature: admin-cases-frontend, Property 5: 路径生成函数正确性
 * Validates: Requirements 7.5, 2.7, 3.11
 */

import { describe, it, expect } from 'vitest'
import fc from 'fast-check'

import { generatePath } from '@/routes/paths'

describe('Property 5: 路径生成函数正确性', () => {
  it('caseDetail generates correct path for any id', () => {
    fc.assert(
      fc.property(fc.nat({ max: 999999 }).map(String), (id) => {
        const path = generatePath.caseDetail(id)
        expect(path).toBe(`/admin/cases/${id}`)
      }),
      { numRuns: 100 },
    )
  })

  it('caseEdit generates correct path for any id', () => {
    fc.assert(
      fc.property(fc.nat({ max: 999999 }).map(String), (id) => {
        const path = generatePath.caseEdit(id)
        expect(path).toBe(`/admin/cases/${id}/edit`)
      }),
      { numRuns: 100 },
    )
  })

  it('caseDetail works with numeric ids', () => {
    fc.assert(
      fc.property(fc.integer({ min: 1, max: 999999 }), (id) => {
        const path = generatePath.caseDetail(id)
        expect(path).toBe(`/admin/cases/${id}`)
      }),
      { numRuns: 100 },
    )
  })

  it('caseEdit works with numeric ids', () => {
    fc.assert(
      fc.property(fc.integer({ min: 1, max: 999999 }), (id) => {
        const path = generatePath.caseEdit(id)
        expect(path).toBe(`/admin/cases/${id}/edit`)
      }),
      { numRuns: 100 },
    )
  })
})
