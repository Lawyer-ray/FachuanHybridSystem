// @vitest-environment jsdom
/**
 * LoginMethodSwitch（登录方式切换器）组件 dom 测试（jsdom）。
 *
 * 覆盖 ARIA tabs 的选中标记、左右方向键切换、两端循环，以及非方向键不触发切换。
 */
import { fireEvent, render, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { LoginMethodSwitch } from './LoginMethodSwitch'

const METHODS = [
  { id: 'password', kind: 'password', label: '账号密码', provider: null },
  { id: 'qr', kind: 'embedded_qr', label: '扫码登录', provider: null },
  { id: 'passkey', kind: 'password', label: '通行密钥', provider: null },
] as const

describe('LoginMethodSwitch', () => {
  it('渲染全部方式并标记选中项', () => {
    const { container } = render(
      <LoginMethodSwitch methods={[...METHODS]} activeId="qr" onChange={vi.fn()} />,
    )
    const tabs = within(container).getAllByRole('tab')
    expect(tabs).toHaveLength(3)
    expect(tabs[1]!.getAttribute('aria-selected')).toBe('true')
    expect(tabs[0]!.getAttribute('aria-selected')).toBe('false')
    container.remove()
  })

  it('ArrowRight 切换到下一项', () => {
    const onChange = vi.fn()
    const { container } = render(
      <LoginMethodSwitch methods={[...METHODS]} activeId="password" onChange={onChange} />,
    )
    fireEvent.keyDown(within(container).getAllByRole('tab')[0]!, { key: 'ArrowRight' })
    expect(onChange).toHaveBeenCalledWith('qr')
    container.remove()
  })

  it('ArrowLeft 切换到上一项', () => {
    const onChange = vi.fn()
    const { container } = render(
      <LoginMethodSwitch methods={[...METHODS]} activeId="qr" onChange={onChange} />,
    )
    fireEvent.keyDown(within(container).getAllByRole('tab')[1]!, { key: 'ArrowLeft' })
    expect(onChange).toHaveBeenCalledWith('password')
    container.remove()
  })

  it('方向键在两端循环', () => {
    const onChange = vi.fn()
    const { container } = render(
      <LoginMethodSwitch methods={[...METHODS]} activeId="passkey" onChange={onChange} />,
    )
    const tabs = within(container).getAllByRole('tab')
    fireEvent.keyDown(tabs[2]!, { key: 'ArrowRight' })
    expect(onChange).toHaveBeenCalledWith('password')

    onChange.mockClear()
    fireEvent.keyDown(tabs[0]!, { key: 'ArrowLeft' })
    expect(onChange).toHaveBeenCalledWith('passkey')
    container.remove()
  })

  it('其他按键不触发切换', () => {
    const onChange = vi.fn()
    const { container } = render(
      <LoginMethodSwitch methods={[...METHODS]} activeId="password" onChange={onChange} />,
    )
    fireEvent.keyDown(within(container).getAllByRole('tab')[0]!, { key: 'Tab' })
    expect(onChange).not.toHaveBeenCalled()
    container.remove()
  })

  it('点击切换', () => {
    const onChange = vi.fn()
    const { container } = render(
      <LoginMethodSwitch methods={[...METHODS]} activeId="password" onChange={onChange} />,
    )
    fireEvent.click(within(container).getByRole('tab', { name: '通行密钥' }))
    expect(onChange).toHaveBeenCalledWith('passkey')
    container.remove()
  })
})
