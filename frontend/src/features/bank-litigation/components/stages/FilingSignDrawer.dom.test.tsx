// @vitest-environment jsdom
/**
 * 签章对照抽屉（`FilingSignDrawer.tsx` 的 `SignDrawer`）单测（jsdom）。
 *
 * - 双图对照可放大成全屏大图，关掉大图回到抽屉
 * - 无签名的那份放大后点名缺失
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DEMO_SIGN_CHECKS } from '../demo-data'
import { SignDrawer } from './FilingSignDrawer'

describe('SignDrawer', () => {
  it('双图对照可放大成全屏大图', () => {
    const failing = DEMO_SIGN_CHECKS.find((d) => !d.sealOk || !d.signOk)!
    render(<SignDrawer name={failing.docName} onClose={() => {}} />)

    fireEvent.click(screen.getAllByRole('button', { name: /放大查看/ })[0]!)
    expect(screen.getByText('印章区域 · 放大查看')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '关闭大图' }))
    expect(screen.queryByText('印章区域 · 放大查看')).toBeNull()
  })

  it('无签名的那份放大后点名缺失', () => {
    const noSign = DEMO_SIGN_CHECKS.find((d) => d.sealOk && !d.signOk)!
    render(<SignDrawer name={noSign.docName} onClose={() => {}} />)

    const zoomButtons = screen.getAllByRole('button', { name: /放大查看/ })
    fireEvent.click(zoomButtons[1]!)
    expect(screen.getByText('签名区域 · 放大查看')).toBeTruthy()
    expect(screen.getByText(/这一份不能送法院/)).toBeTruthy()
  })
})
