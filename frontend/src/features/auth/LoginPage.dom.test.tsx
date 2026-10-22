// @vitest-environment jsdom
/**
 * LoginPage 测试（jsdom）。
 *
 * 重点验证「登录方式派发」与「开场动画播放策略」两条分支：
 * - 已播放过 / 偏好减少动效 → 直接 done，不渲染开场覆盖层
 * - 桌面且有扫码 Provider → 出现方式标签；手机上恒为账密视图
 * - password 视图渲染账密表单 + 通行密钥 + 跳转型社交按钮
 * - embedded_qr 视图渲染二维码面板
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const providersMock = vi.hoisted(() => vi.fn())
const hasPlayedMock = vi.hoisted(() => vi.fn())

vi.mock('./social-api', () => ({
  SOCIAL_PROVIDERS_KEY: ['social', 'providers'],
  socialAuthApi: {
    listProviders: () => providersMock(),
    createSession: vi.fn(),
  },
}))
vi.mock('./intro-cache', () => ({
  hasPlayedIntro: () => hasPlayedMock(),
  markIntroPlayed: vi.fn(),
}))
vi.mock('../../hooks/use-media', () => ({ useMediaQuery: () => mediaDesktop }))
vi.mock('./components/PasswordLoginForm', () => ({ PasswordLoginForm: () => <div>账密表单</div> }))
vi.mock('./components/PasskeyLoginButton', () => ({ PasskeyLoginButton: () => <div>通行密钥按钮</div> }))
vi.mock('./components/SocialQrPanel', () => ({ SocialQrPanel: () => <div>二维码面板</div> }))
vi.mock('./components/SocialRedirectGroup', () => ({
  SocialRedirectGroup: () => <div>跳转型社交按钮组</div>,
}))
vi.mock('./login.css', () => ({}))

let mediaDesktop = true

import { LoginPage } from './LoginPage'

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrap = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
  return render(<LoginPage />, { wrapper: wrap })
}

function provider(name: string, loginMode?: string) {
  return { name, display_name: name, login_mode: loginMode }
}

beforeEach(() => {
  vi.clearAllMocks()
  mediaDesktop = true
  // introSkipped 还会看「减少动态效果」偏好；jsdom 无实现，显式给 false
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  })
  hasPlayedMock.mockReturnValue(true)
  providersMock.mockResolvedValue([])
})

describe('LoginPage：开场动画播放策略', () => {
  it('已播放过：不渲染开场覆盖层，直接进表单', async () => {
    hasPlayedMock.mockReturnValue(true)
    renderPage()
    await waitFor(() => expect(screen.getByText('欢迎回来')).toBeTruthy())
    expect(document.querySelector('.fc-intro')).toBeNull()
  })

  it('未播放过：渲染开场覆盖层', async () => {
    hasPlayedMock.mockReturnValue(false)
    renderPage()
    await waitFor(() => expect(document.querySelector('.fc-intro')).toBeTruthy())
  })
})

describe('LoginPage：账密视图', () => {
  it('无社交 Provider 时只渲染账密表单与通行密钥', async () => {
    const { container } = renderPage()
    await waitFor(() => expect(within(container).getByText('账密表单')).toBeTruthy())
    expect(within(container).getByText('通行密钥按钮')).toBeTruthy()
    expect(within(container).queryByText('跳转型社交按钮组')).toBeNull()
    container.remove()
  })

  it('有跳转型 Provider 时额外渲染社交按钮组', async () => {
    providersMock.mockResolvedValue([provider('github', 'redirect')])
    const { container } = renderPage()
    await waitFor(() => expect(within(container).getByText('跳转型社交按钮组')).toBeTruthy())
    container.remove()
  })

  it('只有一个方式时不渲染方式标签', async () => {
    const { container } = renderPage()
    await waitFor(() => expect(within(container).getByText('账密表单')).toBeTruthy())
    expect(within(container).queryByRole('tablist')).toBeNull()
    container.remove()
  })
})

describe('LoginPage：扫码视图派发', () => {
  it('桌面且有扫码 Provider：出现方式标签', async () => {
    providersMock.mockResolvedValue([provider('feishu', 'embedded_qr')])
    const { container } = renderPage()
    await waitFor(() => expect(within(container).getByRole('tablist')).toBeTruthy())
    const tabs = within(container).getAllByRole('tab')
    expect(tabs).toHaveLength(2)
    container.remove()
  })

  it('手机视口：即使有扫码 Provider 也只显示账密，不出标签', async () => {
    mediaDesktop = false
    providersMock.mockResolvedValue([provider('feishu', 'embedded_qr')])
    const { container } = renderPage()
    await waitFor(() => expect(within(container).getByText('账密表单')).toBeTruthy())
    expect(within(container).queryByRole('tablist')).toBeNull()
    container.remove()
  })
})
