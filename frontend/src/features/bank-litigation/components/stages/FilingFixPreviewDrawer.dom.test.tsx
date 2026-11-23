// @vitest-environment jsdom
/**
 * 一键修正预览抽屉（`FilingFixPreviewDrawer`）单测（jsdom）。
 *
 * - 列出全部 before/after，确认才执行；没打开就不渲染
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DEMO_X3_FIX_DIFF } from '../demo-data'
import { FilingFixPreviewDrawer } from './FilingFixPreviewDrawer'

describe('FilingFixPreviewDrawer', () => {
  it('列出全部 before/after，确认才执行', () => {
    const onConfirm = vi.fn()
    render(
      <FilingFixPreviewDrawer open running={false} onConfirm={onConfirm} onClose={() => {}} />,
    )

    for (const d of DEMO_X3_FIX_DIFF) {
      expect(screen.getByText(d.before)).toBeTruthy()
      expect(screen.getByText(d.after)).toBeTruthy()
    }

    fireEvent.click(screen.getByRole('button', { name: '确认执行' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)

    // 没打开就不渲染
    render(<FilingFixPreviewDrawer open={false} running={false} onConfirm={() => {}} onClose={() => {}} />)
    expect(screen.getAllByText('确认执行')).toHaveLength(1)
  })
})
