// @vitest-environment jsdom
/**
 * SelectionBar 测试（jsdom）。
 *
 * 选页汇总条的一句话说明决定了「合并还是独立成一份」——这是真正会写错的
 * 决策，所以文案与主按钮文案必须由 cross 一致驱动，不能各说各话。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SelectionBar } from './SelectionBar'

describe('SelectionBar', () => {
  it('同源选页：说明「将独立成一份新材料」，按钮同名', () => {
    render(<SelectionBar count={5} cross={false} onClear={vi.fn()} onApply={vi.fn()} />)
    expect(screen.getByText('5 页')).toBeTruthy()
    expect(screen.getByText('来自同一份，将独立成一份新材料')).toBeTruthy()
    expect(screen.getByRole('button', { name: '独立成一份材料' })).toBeTruthy()
  })

  it('跨材料选页：说明「将合并为一份」，按钮同名', () => {
    render(<SelectionBar count={2} cross onClear={vi.fn()} onApply={vi.fn()} />)
    expect(screen.getByText('来自多份材料，将合并为一份')).toBeTruthy()
    expect(screen.getByRole('button', { name: '合并为一份材料' })).toBeTruthy()
  })

  it('取消选择与生成各自回传', () => {
    const onClear = vi.fn()
    const onApply = vi.fn()
    render(<SelectionBar count={1} cross={false} onClear={onClear} onApply={onApply} />)

    fireEvent.click(screen.getByRole('button', { name: '取消选择' }))
    fireEvent.click(screen.getByRole('button', { name: '独立成一份材料' }))

    expect(onClear).toHaveBeenCalledTimes(1)
    expect(onApply).toHaveBeenCalledTimes(1)
  })
})
