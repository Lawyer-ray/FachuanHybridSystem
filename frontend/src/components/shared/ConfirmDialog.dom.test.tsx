// @vitest-environment jsdom
/**
 * components/shared/ConfirmDialog 单测（jsdom）。
 *
 * 锁住三件事：确认/取消各自触发对应回调（不能反）、tone=destructive 用红底按钮、
 * pending 时按住弹窗不关（提交回包前弹窗消失是最常见的返工 bug）。
 * Radix AlertDialog 是模态的，jsdom 下无 pointer-events 布局问题，直接点按钮即可。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ConfirmDialog } from './ConfirmDialog'

function setup(props: Partial<Parameters<typeof ConfirmDialog>[0]> = {}) {
  const onConfirm = vi.fn()
  const onOpenChange = vi.fn()
  const utils = render(
    <ConfirmDialog
      open
      onOpenChange={onOpenChange}
      title="作废这条分享链接？"
      description="作废后客户上传页立即失效，已收到的文件不受影响。"
      onConfirm={onConfirm}
      {...props}
    />,
  )
  return { ...utils, onConfirm, onOpenChange }
}

describe('ConfirmDialog', () => {
  it('渲染标题与说明', () => {
    const { unmount } = setup()
    expect(screen.getByText('作废这条分享链接？')).toBeTruthy()
    expect(screen.getByText(/客户上传页立即失效/)).toBeTruthy()
    unmount()
  })

  it('点确认触发 onConfirm', () => {
    const { onConfirm, onOpenChange, unmount } = setup()
    expect(onOpenChange).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '确定' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
    // Radix 在 Action 点击后自行关闭，回调由 onOpenChange 表达
    expect(onOpenChange.mock.calls.some((c) => c[0] === false)).toBe(true)
    unmount()
  })

  it('点取消不触发 onConfirm，只关弹窗', () => {
    const { onConfirm, onOpenChange, unmount } = setup()
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(onConfirm).not.toHaveBeenCalled()
    expect(onOpenChange.mock.calls.every((c) => c[0] === false)).toBe(true)
    unmount()
  })

  it('自定义按钮文案', () => {
    const { onConfirm, unmount } = setup({ confirmText: '作废', cancelText: '再想想' })
    fireEvent.click(screen.getByRole('button', { name: '作废' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: '再想想' })).toBeTruthy()
    unmount()
  })

  it('tone=destructive 用红底确认按钮，默认不受影响', () => {
    const destructive = setup({ tone: 'destructive' })
    expect(screen.getByRole('button', { name: '确定' }).className).toContain('bg-destructive')
    destructive.unmount()

    const plain = setup()
    expect(screen.getByRole('button', { name: '确定' }).className).not.toContain('bg-destructive')
    plain.unmount()
  })

  it('pending 时文案变「处理中…」且点击不触发 onConfirm（弹窗留住）', () => {
    const { onConfirm, onOpenChange, unmount } = setup({ pending: true })
    expect(onConfirm).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '处理中…' }))
    expect(onConfirm).not.toHaveBeenCalled()
    // 关键：pending 时不能关（preventDefault 挡住 Radix 的自关闭），
    // 否则提交回包前弹窗就消失，用户看不到失败原因
    expect(onOpenChange.mock.calls.some((c) => c[0] === false)).toBe(false)
    unmount()
  })

  it('open=false 时不渲染内容', () => {
    const { unmount } = setup({ open: false })
    expect(screen.queryByText('作废这条分享链接？')).toBeNull()
    unmount()
  })
})
