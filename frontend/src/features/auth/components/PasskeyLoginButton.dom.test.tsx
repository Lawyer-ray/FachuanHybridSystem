// @vitest-environment jsdom
/**
 * PasskeyLoginButton 组件 dom 测试（jsdom）。
 *
 * mock 边界：passkey-api（网络）、store（用户态）、react-router（导航断言）、
 * navigator.credentials（系统认证器）。覆盖：支持时渲染、成功流（setUser +
 * 导航首页）、NotAllowedError 指引文案、其他错误透传。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mockNavigate = vi.fn()
const mockSetUser = vi.fn()

vi.mock('react-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router')>()),
  useNavigate: () => mockNavigate,
}))

vi.mock('../store', () => ({
  useAuth: (selector: (state: unknown) => unknown) =>
    selector({ user: null, setUser: mockSetUser }),
}))

vi.mock('../passkey-api', () => ({
  passkeyApi: {
    loginOptions: vi.fn(),
    loginVerify: vi.fn(),
  },
}))

import { PasskeyLoginButton } from './PasskeyLoginButton'
import { passkeyApi } from '../passkey-api'

const encoder = new TextEncoder()

function fakeAssertionCredential() {
  return {
    id: 'cred-1',
    rawId: encoder.encode('raw').buffer,
    type: 'public-key',
    response: {
      clientDataJSON: encoder.encode('{}').buffer,
      authenticatorData: encoder.encode('auth').buffer,
      signature: encoder.encode('sig').buffer,
      userHandle: null,
    },
  }
}

/** jsdom 没有 WebAuthn：注入平台认证器可用的假实现 */
function stubWebauthn(available: boolean) {
  Object.defineProperty(window, 'PublicKeyCredential', {
    value: {
      isUserVerifyingPlatformAuthenticatorAvailable: vi.fn(async () => available),
    },
    configurable: true,
  })
  Object.defineProperty(navigator, 'credentials', {
    value: { get: vi.fn(), create: vi.fn() },
    configurable: true,
  })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('PasskeyLoginButton', () => {
  it('平台认证器可用时渲染按钮', async () => {
    stubWebauthn(true)
    render(<PasskeyLoginButton />)
    expect(await screen.findByRole('button', { name: '使用通行密钥登录' })).toBeTruthy()
  })

  it('不支持 WebAuthn 时不渲染', async () => {
    stubWebauthn(false)
    render(<PasskeyLoginButton />)
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: '使用通行密钥登录' })).not.toBeTruthy()
    })
  })

  it('成功流：验证后写入用户态并进入首页', async () => {
    stubWebauthn(true)
    vi.mocked(passkeyApi.loginOptions).mockResolvedValue({ rpId: 'localhost', challenge: 'NDI' })
    vi.mocked(navigator.credentials.get).mockResolvedValue(fakeAssertionCredential())
    vi.mocked(passkeyApi.loginVerify).mockResolvedValue({
      success: true,
      access: 'access-token',
      refresh: 'refresh-token',
      user_id: 7,
      username: 'lawyer-wang',
      message: '',
    })

    render(<PasskeyLoginButton />)
    fireEvent.click(await screen.findByRole('button', { name: '使用通行密钥登录' }))

    await waitFor(() => {
      expect(mockSetUser).toHaveBeenCalledWith({ id: 7, username: 'lawyer-wang' })
      expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true })
    })
    expect(passkeyApi.loginVerify).toHaveBeenCalledTimes(1)
    // 按钮保持 pending 到导航发生（防双击），不回退到可点状态
    expect((screen.getByRole('button') as HTMLButtonElement).disabled).toBe(true)
  })

  it('NotAllowedError 给出「去账号绑定添加」指引', async () => {
    stubWebauthn(true)
    vi.mocked(passkeyApi.loginOptions).mockResolvedValue({ rpId: 'localhost', challenge: 'NDI' })
    vi.mocked(navigator.credentials.get).mockRejectedValue(
      new DOMException('user cancelled', 'NotAllowedError'),
    )

    render(<PasskeyLoginButton />)
    fireEvent.click(await screen.findByRole('button', { name: '使用通行密钥登录' }))

    expect(await screen.findByText(/「账号绑定」中添加/)).toBeTruthy()
  })

  it('其他错误透传后端文案', async () => {
    stubWebauthn(true)
    vi.mocked(passkeyApi.loginOptions).mockRejectedValue(new Error('通行密钥会话已过期，请重新操作'))

    render(<PasskeyLoginButton />)
    fireEvent.click(await screen.findByRole('button', { name: '使用通行密钥登录' }))

    expect(await screen.findByText('通行密钥会话已过期，请重新操作')).toBeTruthy()
  })
})
