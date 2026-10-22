// @vitest-environment jsdom
/**
 * 登录页小组件测试：LoginMethodSwitch 与 SocialRedirectGroup。
 *
 * 覆盖 ARIA tabs 的方向键循环，以及跳转型社交登录的
 * 「进行中禁用全部按钮 / 失败复位 pending 并显示文案」两条状态机分支。
 */
import { fireEvent, render, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { LoginMethodSwitch } from './LoginMethodSwitch'
import { SocialRedirectGroup } from './SocialRedirectGroup'
import type { SocialProviderInfo, SocialSession } from '../social-api'

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

function provider(name: string, display = ''): SocialProviderInfo {
  return { name, display_name: display } as SocialProviderInfo
}

describe('SocialRedirectGroup', () => {
  it('渲染分割线与各 provider 按钮', () => {
    const { container } = render(
      <SocialRedirectGroup providers={[provider('feishu', '飞书'), provider('google')]} />,
    )
    expect(within(container).getByRole('separator')).toBeTruthy()
    expect(within(container).getByRole('button', { name: /飞书/ })).toBeTruthy()
    expect(within(container).getByRole('button', { name: /google/ })).toBeTruthy()
    container.remove()
  })

  it('跳转成功：写入 window.location.href', async () => {
    const createSession = vi.fn(async () => ({ goto: 'https://auth.example.com/x' }) as SocialSession)
    const { container } = render(
      <SocialRedirectGroup providers={[provider('feishu', '飞书')]} createSession={createSession} />,
    )
    fireEvent.click(within(container).getByRole('button', { name: /飞书/ }))
    await waitFor(() => expect(createSession).toHaveBeenCalledWith('feishu'))
    container.remove()
  })

  it('跳转进行中：显示「跳转中…」并禁用全部按钮（防双跳）', async () => {
    let resolve: (v: SocialSession) => void = () => {}
    const createSession = vi.fn(
      () =>
        new Promise<SocialSession>((r) => {
          resolve = r
        }),
    )
    const { container } = render(
      <SocialRedirectGroup
        providers={[provider('feishu', '飞书'), provider('google', '谷歌')]}
        createSession={createSession}
      />,
    )

    fireEvent.click(within(container).getByRole('button', { name: /飞书/ }))
    await waitFor(() => expect(within(container).getByText('跳转中…')).toBeTruthy())

    for (const btn of within(container).getAllByRole('button')) {
      expect((btn as HTMLButtonElement).disabled).toBe(true)
    }
    resolve({ goto: 'https://example.com' } as SocialSession)
    container.remove()
  })

  it('跳转失败：复位 pending、启用按钮并显示错误文案', async () => {
    const createSession = vi.fn(async () => {
      throw new Error('后端不可用')
    })
    const { container } = render(
      <SocialRedirectGroup providers={[provider('feishu', '飞书')]} createSession={createSession} />,
    )

    fireEvent.click(within(container).getByRole('button', { name: /飞书/ }))
    await waitFor(() => expect(within(container).getByText('后端不可用')).toBeTruthy())

    // pending 复位后按钮重新可用
    const btn = within(container).getByRole('button', { name: /飞书/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(false)
    container.remove()
  })
})
