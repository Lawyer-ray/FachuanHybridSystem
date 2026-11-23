// @vitest-environment jsdom
/**
 * 三处金额对照卡（`FilingAmountCard`）单测（jsdom）。
 *
 * - 差异行标红并给出差额，点开看计算口径
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DEMO_X3_AMOUNTS } from '../demo-data'
import { FilingAmountCard } from './FilingAmountCard'

describe('FilingAmountCard', () => {
  it('差异行标红并给出差额，点开看口径', () => {
    const diffs = DEMO_X3_AMOUNTS.filter((a) => !a.consistent)
    render(<FilingAmountCard />)

    expect(screen.getByText(`${diffs.length} 处不一致`)).toBeTruthy()
    // 罚息行与合计行都差 31.85，所以按条数断言而不是唯一性
    expect(screen.getAllByText(`+${diffs[0]!.delta}`)).toHaveLength(diffs.length)

    fireEvent.click(screen.getByText(diffs[0]!.item))
    expect(screen.getByText(`${diffs[0]!.item} · 计算口径`)).toBeTruthy()
    expect(screen.getByText(diffs[0]!.basis)).toBeTruthy()
  })
})
