// @vitest-environment jsdom
/**
 * ConfirmDeleteDialog 测试（jsdom）。
 *
 * 它是 DeskPage（删材料包）与 Reader（删页）共用的破坏性确认框，外壳收敛到
 * 共享 ConfirmDialog 后，本文件只守本 feature 的 props 形状：
 * - label 决定确认按钮文案；
 * - pending 时确认按钮被拦住（提交没回包前框不能消失），关闭回调不被触发。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ConfirmDeleteDialog } from './ConfirmDeleteDialog'

describe('ConfirmDeleteDialog', () => {
  it('渲染标题、说明与默认「删除」文案', () => {
    render(
      <ConfirmDeleteDialog open onOpenChange={vi.fn()} title="删除「材料包 A」？" description="不可恢复" onConfirm={vi.fn()} />,
    )
    expect(screen.getByText('删除「材料包 A」？')).toBeTruthy()
    expect(screen.getByText('不可恢复')).toBeTruthy()
    expect(screen.getByRole('button', { name: '删除' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '取消' })).toBeTruthy()
  })

  it('label 覆盖确认按钮文案', () => {
    render(
      <ConfirmDeleteDialog open onOpenChange={vi.fn()} title="t" description="d" label="移出" onConfirm={vi.fn()} />,
    )
    expect(screen.getByRole('button', { name: '移出' })).toBeTruthy()
  })

  it('点确认回传 onConfirm（非 pending 时）', () => {
    const onConfirm = vi.fn()
    render(<ConfirmDeleteDialog open onOpenChange={vi.fn()} title="t" description="d" onConfirm={onConfirm} />)
    fireEvent.click(screen.getByRole('button', { name: '删除' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('pending：确认按钮换成「处理中…」且不重复触发（提交未回包框不能消失）', () => {
    const onConfirm = vi.fn()
    render(
      <ConfirmDeleteDialog open pending onOpenChange={vi.fn()} title="t" description="d" onConfirm={onConfirm} />,
    )
    expect((screen.getByRole('button', { name: '取消' }) as HTMLButtonElement).disabled).toBe(true)

    const busy = screen.getByRole('button', { name: '处理中…' })
    fireEvent.click(busy)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('open=false 时不渲染内容', () => {
    render(<ConfirmDeleteDialog open={false} onOpenChange={vi.fn()} title="不该出现" description="d" onConfirm={vi.fn()} />)
    expect(screen.queryByText('不该出现')).toBeNull()
  })
})
