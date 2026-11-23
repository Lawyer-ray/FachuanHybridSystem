// @vitest-environment jsdom
/**
 * 委托合同条款卡与条款编辑抽屉（`ContractTermsCard.tsx` 的两个导出）单测（jsdom）。
 *
 * - ContractTermsCard：每条都有编辑按钮、未填项标「未填」、改过的行打「已修改」
 * - TermEditDrawer：保存时把改后的文本交给上层
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DEMO_CONTRACT_TERMS } from '../demo-data'
import { ContractTermsCard, TermEditDrawer } from './ContractTermsCard'
import { initTermDrafts, pendingTermCount } from './contract-terms'

describe('ContractTermsCard', () => {
  it('每条都有编辑按钮，未填项标「未填」', () => {
    const onEdit = vi.fn()
    render(<ContractTermsCard drafts={initTermDrafts()} onEdit={onEdit} />)

    expect(screen.getAllByRole('button', { name: /编辑/ })).toHaveLength(DEMO_CONTRACT_TERMS.length)
    const unfilled = DEMO_CONTRACT_TERMS.filter((t) => !t.filled)
    expect(screen.getAllByText('未填')).toHaveLength(unfilled.length)

    fireEvent.click(screen.getAllByRole('button', { name: /编辑/ })[0]!)
    expect(onEdit).toHaveBeenCalledWith(DEMO_CONTRACT_TERMS[0]!.clause)
  })

  it('改过的行打「已修改」，不再算待定', () => {
    const drafts = initTermDrafts()
    const clause = DEMO_CONTRACT_TERMS.find((t) => !t.filled)!.clause
    drafts[clause] = { value: '改过的特别授权', edited: true }
    render(<ContractTermsCard drafts={drafts} onEdit={() => {}} />)

    expect(screen.getByText('已修改')).toBeTruthy()
    // 8 条里只有 1 条本来「待定」，改过之后全部确认
    expect(pendingTermCount(drafts)).toBeLessThan(
      DEMO_CONTRACT_TERMS.filter((t) => !t.filled).length,
    )
    expect(screen.getByText('全部确认')).toBeTruthy()
  })
})

describe('TermEditDrawer', () => {
  it('保存时把改后的文本交给上层', () => {
    const clause = DEMO_CONTRACT_TERMS.find((t) => !t.filled)!.clause
    const onSave = vi.fn()
    render(
      <TermEditDrawer clause={clause} drafts={initTermDrafts()} onSave={onSave} onClose={() => {}} />,
    )

    const box = screen.getByRole('textbox')
    const typed = '代为和解、代收款项'
    fireEvent.change(box, { target: { value: typed } })
    fireEvent.click(screen.getByRole('button', { name: '保存修改' }))

    expect(onSave).toHaveBeenCalledTimes(1)
    const [savedClause, savedValue] = vi.mocked(onSave).mock.calls[0]!
    expect(savedClause).toBe(clause)
    // 保存的是输入框里那一版（不是自动填充原文）
    expect(savedValue).not.toBe('')
    expect(savedValue).toBe(typed)
  })
})
