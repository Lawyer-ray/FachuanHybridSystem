/**
 * 委托合同条款草稿模型的单测（node，不需要 DOM）。
 *
 * - initTermDrafts：以演示条款为初值
 * - pendingTermCount：只数「本来未填且没被律师改过」的项
 */
import { describe, expect, it } from 'vitest'

import { DEMO_CONTRACT_TERMS } from '../demo-data'
import { initTermDrafts, pendingTermCount } from './contract-terms'

describe('contract-terms', () => {
  it('初始草稿取自动填充值，未填项计入待定数', () => {
    const drafts = initTermDrafts()
    expect(Object.keys(drafts)).toHaveLength(DEMO_CONTRACT_TERMS.length)
    const unfilled = DEMO_CONTRACT_TERMS.filter((t) => !t.filled).length
    expect(pendingTermCount(drafts)).toBe(unfilled)
    expect(unfilled).toBeGreaterThan(0)

    // 律师改过就不再算待定
    const clause = DEMO_CONTRACT_TERMS.find((t) => !t.filled)!.clause
    drafts[clause] = { value: '代为和解、代收法律文书及执行款项', edited: true }
    expect(pendingTermCount(drafts)).toBe(unfilled - 1)
  })
})
