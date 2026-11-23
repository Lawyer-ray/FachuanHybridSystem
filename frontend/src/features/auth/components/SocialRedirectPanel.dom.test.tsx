// @vitest-environment jsdom
/**
 * SocialRedirectPanel（整页跳转型社交登录面板）组件 dom 测试（jsdom）。
 *
 * mock 边界：不碰 ../social-api——createSession 全部由 props 注入（绑定页传
 * bind-session，登录页用默认登录 session）。覆盖：按钮与跳转指引文案渲染、
 * 跳转成功、失败复位 loading 并显示错误文案（后端消息 / 无消息时的兜底文案）。
 */
import { fireEvent, render, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SocialRedirectPanel } from './SocialRedirectPanel'
import { SOCIAL_REDIRECT_FAIL_TEXT } from '../constants'
import type { SocialProviderInfo, SocialSession } from '../types'

const GOOGLE = { name: 'google', display_name: 'Google' } as SocialProviderInfo

describe('SocialRedirectPanel', () => {
  it('渲染跳转按钮与授权指引文案', () => {
    const { container } = render(<SocialRedirectPanel provider={GOOGLE} />)
    expect(within(container).getByRole('button', { name: '使用 Google 登录' })).toBeTruthy()
    expect(within(container).getByText('将跳转到 Google 完成授权')).toBeTruthy()
    container.remove()
  })

  it('跳转成功：用传入的 createSession 发起授权会话', async () => {
    const createSession = vi.fn(async () => ({ goto: 'https://auth.example.com/x' }) as SocialSession)
    const { container } = render(<SocialRedirectPanel provider={GOOGLE} createSession={createSession} />)

    fireEvent.click(within(container).getByRole('button', { name: '使用 Google 登录' }))
    await waitFor(() => expect(createSession).toHaveBeenCalledWith('google'))
    container.remove()
  })

  it('跳转失败：复位 loading、按钮可再点并显示后端错误文案', async () => {
    const createSession = vi.fn(async () => {
      throw new Error('该平台未配置')
    })
    const { container } = render(<SocialRedirectPanel provider={GOOGLE} createSession={createSession} />)

    fireEvent.click(within(container).getByRole('button', { name: '使用 Google 登录' }))
    await waitFor(() => expect(within(container).getByText('该平台未配置')).toBeTruthy())

    const btn = within(container).getByRole('button', { name: '使用 Google 登录' }) as HTMLButtonElement
    expect(btn.disabled).toBe(false)
    container.remove()
  })

  it('跳转失败且错误无文案：显示兜底文案', async () => {
    const createSession = vi.fn(async () => {
      throw new Error('')
    })
    const { container } = render(<SocialRedirectPanel provider={GOOGLE} createSession={createSession} />)

    fireEvent.click(within(container).getByRole('button', { name: '使用 Google 登录' }))
    await waitFor(() => expect(within(container).getByText(SOCIAL_REDIRECT_FAIL_TEXT)).toBeTruthy())
    container.remove()
  })
})
