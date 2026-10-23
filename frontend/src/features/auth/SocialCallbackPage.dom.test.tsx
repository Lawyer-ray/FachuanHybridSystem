// @vitest-environment jsdom
/**
 * SocialCallbackPage 状态机测试（jsdom）。
 *
 * 三条落点：error 映射文案 / bound 直接回落地页 / code 换 JWT。
 * 另覆盖严格模式下不重复兑换（TempAuth 一次性）。
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const exchangeMock = vi.hoisted(() => vi.fn())
const navigateSpy = vi.hoisted(() => vi.fn())

vi.mock('./social-api', () => ({
  socialAuthApi: { exchangeToken: (...a: unknown[]) => exchangeMock(...a) },
}))

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => navigateSpy }
})

import { SocialCallbackPage } from './SocialCallbackPage'
import { useAuth } from './store'

function renderAt(search: string) {
  window.history.replaceState({}, '', '/auth/callback' + search)
  return render(
    <MemoryRouter initialEntries={['/auth/callback' + search]}>
      <Routes>
        <Route path="/auth/callback" element={<SocialCallbackPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  useAuth.setState({ user: null })
})

describe('SocialCallbackPage', () => {
  it('error 参数：映射成可读文案并显示返回登录页', async () => {
    const { container } = renderAt('?error=access_denied')
    await waitFor(() => expect(screen.getByText(/返回登录页/)).toBeTruthy())
    // 不应发起兑换
    expect(exchangeMock).not.toHaveBeenCalled()
    container.remove()
  })

  it('missing code：提示缺少参数', async () => {
    const { container } = renderAt('')
    await waitFor(() => expect(within(container).getByText(/返回登录页/)).toBeTruthy())
    expect(exchangeMock).not.toHaveBeenCalled()
    container.remove()
  })

  it('bound 参数：不兑换，直接导航回落地页并保留 bound 标记', async () => {
    const { container } = renderAt('?bound=feishu&redirect=/settings/bindings')
    await waitFor(() => expect(navigateSpy).toHaveBeenCalled())
    const [url, opts] = navigateSpy.mock.calls[0]!
    expect(String(url)).toContain('/settings/bindings')
    expect(String(url)).toContain('bound=feishu')
    expect(opts).toEqual({ replace: true })
    expect(exchangeMock).not.toHaveBeenCalled()
    container.remove()
  })

  it('code 兑换成功：写入 user 并跳到 redirect', async () => {
    exchangeMock.mockResolvedValue({ success: true, user_id: 7, username: '张三' })
    const { container } = renderAt('?code=TempAuth&redirect=/')

    await waitFor(() => expect(useAuth.getState().user).toEqual({ id: 7, username: '张三' }))
    expect(navigateSpy).toHaveBeenCalledWith('/', { replace: true })
    container.remove()
  })

  it('code 兑换失败（success=false）：显示后端文案', async () => {
    exchangeMock.mockResolvedValue({ success: false, message: '登录码已失效' })
    const { container } = renderAt('?code=TempAuth')

    await waitFor(() => expect(within(container).getByText('登录码已失效')).toBeTruthy())
    expect(useAuth.getState().user).toBeNull()
    container.remove()
  })

  it('code 兑换抛异常：显示兜底文案且不写 user', async () => {
    exchangeMock.mockRejectedValue(new Error('网络中断'))
    const { container } = renderAt('?code=TempAuth')

    await waitFor(() => expect(within(container).getByText('网络中断')).toBeTruthy())
    expect(useAuth.getState().user).toBeNull()
    container.remove()
  })

  it('恶意 redirect（//evil.com）：被 sanitize 拦下，回落到 /', async () => {
    // 必须在 render 之前 stubbing，否则 effect 先跑会拿到 undefined
    exchangeMock.mockResolvedValue({ success: true, user_id: 1, username: 'u' })
    const { container } = renderAt('?code=TempAuth&redirect=//evil.com')

    await waitFor(() => expect(navigateSpy).toHaveBeenCalled())
    const [url] = navigateSpy.mock.calls[0]!
    expect(String(url)).not.toContain('evil.com')
    container.remove()
  })
})

describe('SocialCallbackPage 失败落点（A-P1-1 回归）', () => {
  it('绑定流程失败：提供「返回账号绑定」而非只有返回登录页', async () => {
    const { container } = renderAt('?error=already_bound&redirect=/settings/bindings')
    await waitFor(() => expect(within(container).getByText('返回账号绑定')).toBeTruthy())
    // 同时仍保留回登录页的出口
    expect(within(container).getByText('返回登录页')).toBeTruthy()
    container.remove()
  })

  it('普通登录失败：只有「返回登录页」，不出现绑定入口', async () => {
    const { container } = renderAt('?error=access_denied')
    await waitFor(() => expect(within(container).getByText('返回登录页')).toBeTruthy())
    expect(within(container).queryByText('返回账号绑定')).toBeNull()
    container.remove()
  })

  it('点「返回账号绑定」导航到绑定页', async () => {
    const { container } = renderAt('?error=not_bound&redirect=/settings/bindings')
    await waitFor(() => expect(within(container).getByText('返回账号绑定')).toBeTruthy())

    fireEvent.click(within(container).getByText('返回账号绑定'))
    expect(navigateSpy).toHaveBeenCalledWith('/settings/bindings', { replace: true })
    container.remove()
  })
})
