// @vitest-environment jsdom
/**
 * LoginMethodSwitch（登录方式切换器）组件 dom 测试（jsdom）。
 *
 * 语义是单选（radiogroup + radio，aria-checked）：覆盖选中标记、roving tabindex、
 * 左右方向键「移动焦点并选中」、两端循环，以及非方向键不触发切换。
 */
import { fireEvent, render, within } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { LoginMethodSwitch } from './LoginMethodSwitch'

const METHODS = [
  { id: 'password', kind: 'password', label: '账号密码', provider: null },
  { id: 'qr', kind: 'embedded_qr', label: '扫码登录', provider: null },
  { id: 'passkey', kind: 'password', label: '通行密钥', provider: null },
] as const

/** 受控包装：真实用法里 activeId 由父级状态驱动，方向键后要看得到 aria-checked/tabIndex 更新 */
function Harness({ initialId }: { initialId: string }) {
  const [activeId, setActiveId] = useState(initialId)
  return <LoginMethodSwitch methods={[...METHODS]} activeId={activeId} onChange={setActiveId} />
}

describe('LoginMethodSwitch', () => {
  it('渲染为单选组并标记选中项', () => {
    const { container } = render(
      <LoginMethodSwitch methods={[...METHODS]} activeId="qr" onChange={vi.fn()} />,
    )
    expect(within(container).getByRole('radiogroup', { name: '登录方式' })).toBeTruthy()
    const radios = within(container).getAllByRole('radio')
    expect(radios).toHaveLength(3)
    expect(radios[1]!.getAttribute('aria-checked')).toBe('true')
    expect(radios[0]!.getAttribute('aria-checked')).toBe('false')
    expect(radios[1]!.getAttribute('aria-selected')).toBeNull()
    container.remove()
  })

  it('roving tabindex：只有选中项进 Tab 顺序', () => {
    const { container } = render(
      <LoginMethodSwitch methods={[...METHODS]} activeId="qr" onChange={vi.fn()} />,
    )
    const radios = within(container).getAllByRole('radio')
    expect(radios.map((radio) => radio.tabIndex)).toEqual([-1, 0, -1])
    container.remove()
  })

  it('ArrowRight 切换到下一项', () => {
    const onChange = vi.fn()
    const { container } = render(
      <LoginMethodSwitch methods={[...METHODS]} activeId="password" onChange={onChange} />,
    )
    fireEvent.keyDown(within(container).getAllByRole('radio')[0]!, { key: 'ArrowRight' })
    expect(onChange).toHaveBeenCalledWith('qr')
    container.remove()
  })

  it('ArrowLeft 切换到上一项', () => {
    const onChange = vi.fn()
    const { container } = render(
      <LoginMethodSwitch methods={[...METHODS]} activeId="qr" onChange={onChange} />,
    )
    fireEvent.keyDown(within(container).getAllByRole('radio')[1]!, { key: 'ArrowLeft' })
    expect(onChange).toHaveBeenCalledWith('password')
    container.remove()
  })

  it('ArrowRight 移动焦点并选中下一项', () => {
    const { container } = render(<Harness initialId="password" />)
    const radios = within(container).getAllByRole('radio')
    radios[0]!.focus()
    fireEvent.keyDown(radios[0]!, { key: 'ArrowRight' })
    expect(radios[1]!.getAttribute('aria-checked')).toBe('true')
    expect(radios[1]!.tabIndex).toBe(0)
    expect(radios[0]!.tabIndex).toBe(-1)
    expect(document.activeElement).toBe(radios[1])
    container.remove()
  })

  it('方向键在两端循环', () => {
    const onChange = vi.fn()
    const { container } = render(
      <LoginMethodSwitch methods={[...METHODS]} activeId="passkey" onChange={onChange} />,
    )
    const radios = within(container).getAllByRole('radio')
    fireEvent.keyDown(radios[2]!, { key: 'ArrowRight' })
    expect(onChange).toHaveBeenCalledWith('password')

    onChange.mockClear()
    fireEvent.keyDown(radios[0]!, { key: 'ArrowLeft' })
    expect(onChange).toHaveBeenCalledWith('passkey')
    container.remove()
  })

  it('其他按键不触发切换', () => {
    const onChange = vi.fn()
    const { container } = render(
      <LoginMethodSwitch methods={[...METHODS]} activeId="password" onChange={onChange} />,
    )
    fireEvent.keyDown(within(container).getAllByRole('radio')[0]!, { key: 'Tab' })
    expect(onChange).not.toHaveBeenCalled()
    container.remove()
  })

  it('点击切换', () => {
    const onChange = vi.fn()
    const { container } = render(
      <LoginMethodSwitch methods={[...METHODS]} activeId="password" onChange={onChange} />,
    )
    fireEvent.click(within(container).getByRole('radio', { name: '通行密钥' }))
    expect(onChange).toHaveBeenCalledWith('passkey')
    container.remove()
  })
})
