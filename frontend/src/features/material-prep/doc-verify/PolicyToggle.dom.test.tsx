// @vitest-environment jsdom
/**
 * 「回传后核对内容」勾选框（jsdom）。
 *
 * 它是纯受控组件：勾选值来自 props、变化交给 onChange，组件自己不留状态。
 * 锁三件事——文案（四类文书 + 副提示，律师据此知道勾了会发生什么）、
 * 勾选态跟随 props、点一下把**新值**交给回调（传反了等于偏好永远反着存）。
 */
import { fireEvent, render, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { PolicyToggle } from './PolicyToggle'

function renderToggle(checked: boolean, onChange = vi.fn()) {
  const { container } = render(<PolicyToggle checked={checked} onChange={onChange} />)
  const box = within(document.body).getByRole('checkbox', {
    name: /回传后核对内容/,
  }) as HTMLInputElement
  return { container, box, onChange }
}

describe('PolicyToggle：回传后核对内容', () => {
  it('文案点名四类文书，并写清「逐页比完整本 + 扫描件走本地 OCR」的副提示', () => {
    const { container } = renderToggle(true)

    const text = document.body.textContent ?? ''
    expect(text).toContain('起诉状')
    expect(text).toContain('授权委托书')
    expect(text).toContain('送达地址确认书')
    expect(text).toContain('退费账户确认书')
    // 默认不再只核前 N 页：写清「逐页整本」与「扫描件走 OCR」，律师才知道要等多久
    expect(text).toContain('逐页比对整本正文')
    container.remove()
  })

  it('勾选态跟随 props（受控）', () => {
    const { container, box } = renderToggle(true)

    expect(box.checked).toBe(true)
    container.remove()
  })

  it('取消勾选：回调收到 false，且组件自己不翻转（等 props 改）', () => {
    const { container, box, onChange } = renderToggle(true)

    fireEvent.click(box)

    expect(onChange).toHaveBeenCalledWith(false)
    expect(box.checked).toBe(true)
    container.remove()
  })

  it('勾上：回调收到 true', () => {
    const { container, box, onChange } = renderToggle(false)

    expect(box.checked).toBe(false)
    fireEvent.click(box)
    expect(onChange).toHaveBeenCalledWith(true)
    container.remove()
  })
})
