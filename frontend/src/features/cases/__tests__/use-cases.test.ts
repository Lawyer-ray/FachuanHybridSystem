/**
 * Property 2: 查询键包含筛选参数
 *
 * For any 筛选参数组合（case_type, status），casesQueryKey(filters)
 * 生成的查询键数组应包含这些筛选参数值，且不同筛选参数组合应生成不同的查询键。
 *
 * Feature: admin-cases-frontend, Property 2: 查询键包含筛选参数
 * Validates: Requirements 2.4, 6.2
 */

import { describe, it, expect } from 'vitest'
import fc from 'fast-check'

import { casesQueryKey } from '../hooks/use-cases'

const caseTypeArb = fc.constantFrom('civil', 'administrative', 'criminal', 'execution', 'bankruptcy', undefined)
const statusArb = fc.constantFrom('active', 'closed', undefined)

describe('Property 2: 查询键包含筛选参数', () => {
  it('query key contains filter params', () => {
    fc.assert(
      fc.property(caseTypeArb, statusArb, (caseType, status) => {
        const filters = {
          ...(caseType ? { case_type: caseType as 'civil' } : {}),
          ...(status ? { status } : {}),
        }
        const key = casesQueryKey(filters)

        // Key should be an array starting with 'cases'
        expect(key[0]).toBe('cases')

        // The filters object should be in the key
        const keyFilters = key[1] as Record<string, unknown>
        if (caseType) {
          expect(keyFilters.case_type).toBe(caseType)
        }
        if (status) {
          expect(keyFilters.status).toBe(status)
        }
      }),
      { numRuns: 100 },
    )
  })

  it('different filter combos produce different keys', () => {
    fc.assert(
      fc.property(caseTypeArb, statusArb, caseTypeArb, statusArb, (ct1, s1, ct2, s2) => {
        const f1 = { ...(ct1 ? { case_type: ct1 as 'civil' } : {}), ...(s1 ? { status: s1 } : {}) }
        const f2 = { ...(ct2 ? { case_type: ct2 as 'civil' } : {}), ...(s2 ? { status: s2 } : {}) }
        const k1 = casesQueryKey(f1)
        const k2 = casesQueryKey(f2)

        if (JSON.stringify(f1) !== JSON.stringify(f2)) {
          expect(JSON.stringify(k1)).not.toBe(JSON.stringify(k2))
        }
      }),
      { numRuns: 100 },
    )
  })
})
