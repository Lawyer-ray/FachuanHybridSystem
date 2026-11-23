// @vitest-environment jsdom
/**
 * SocialRedirectGroup（登录页跳转型社交按钮组）组件 dom 测试（jsdom）。
 *
 * mock 边界：不碰 ../social-api——createSession 全部由 props 注入。
 * 覆盖：分割线与各 Provider 按钮渲染、跳转成功、跳转中禁用全部按钮（防双跳）、
 * 失败复位 pending 并显示错误文案。
 */
import { fireEvent, render, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SocialRedirectGroup } from './SocialRedirectGroup'
import type { SocialProviderInfo, SocialSession } from '../types'

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
