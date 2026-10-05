// @vitest-environment jsdom
/**
 * PasskeySection 组件 dom 测试（jsdom）。
 *
 * mock 边界：passkey-api（网络）、sonner（toast）。覆盖：凭据列表渲染、
 * 删除确认流（AlertDialog → remove）、重命名行内编辑（PATCH）、添加成功流
 * （create → registerVerify → invalidate）、不支持时不给添加入口。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

const mockList = vi.fn()
const mockRemove = vi.fn()
const mockRename = vi.fn()
const mockRegisterOptions = vi.fn()
const mockRegisterVerify = vi.fn()

vi.mock('../passkey-api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../passkey-api')>()),
  passkeyApi: {
    list: (...args: unknown[]) => mockList(...args),
    remove: (...args: unknown[]) => mockRemove(...args),
    rename: (...args: unknown[]) => mockRename(...args),
    registerOptions: (...args: unknown[]) => mockRegisterOptions(...args),
    registerVerify: (...args: unknown[]) => mockRegisterVerify(...args),
  },
}))

import { PasskeySection } from './PasskeySection'
import { toast } from 'sonner'

const encoder = new TextEncoder()

function renderSection() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PasskeySection />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function stubWebauthn(available: boolean) {
  Object.defineProperty(window, 'PublicKeyCredential', {
    value: available
      ? { isUserVerifyingPlatformAuthenticatorAvailable: vi.fn(async () => true) }
      : undefined,
    configurable: true,
  })
  Object.defineProperty(navigator, 'credentials', {
    value: { get: vi.fn(), create: vi.fn() },
    configurable: true,
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  stubWebauthn(true)
  mockList.mockResolvedValue([
    {
      id: 1,
      name: 'MacBook Touch ID',
      rp_id: 'localhost',
      created_at: '2026-10-05T00:00:00Z',
      last_used_at: null,
    },
    {
      id: 2,
      name: 'iPhone',
      rp_id: 'app.xlaw.top',
      created_at: '2026-10-04T00:00:00Z',
      last_used_at: '2026-10-05T08:00:00Z',
    },
  ])
})

describe('PasskeySection', () => {
  it('渲染凭据列表与元信息', async () => {
    renderSection()
    expect(await screen.findByText('MacBook Touch ID')).toBeTruthy()
    expect(screen.getByText('iPhone')).toBeTruthy()
    expect(screen.getByText(/从未使用/)).toBeTruthy()
    expect(screen.getByText(/app\.xlaw\.top/)).toBeTruthy()
    expect(screen.getByRole('button', { name: '添加通行密钥' })).toBeTruthy()
  })

  it('删除走确认弹窗，确认后调用 remove', async () => {
    mockRemove.mockResolvedValue(undefined)
    renderSection()
    // 第一行的删除按钮
    fireEvent.click((await screen.findAllByRole('button', { name: '删除' }))[0]!)
    // 弹窗出现，取消不应删除
    expect(await screen.findByText(/删除后该设备将无法再用通行密钥登录/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(mockRemove).not.toHaveBeenCalled()

    // 重新点删除，确认（弹窗内确认按钮文案同为「删除」，是最后一个）
    fireEvent.click((screen.getAllByRole('button', { name: '删除' }))[0]!)
    const confirmButton = (await screen.findAllByRole('button', { name: '删除' })).at(-1)
    fireEvent.click(confirmButton!)
    await waitFor(() => expect(mockRemove).toHaveBeenCalledWith(1))
    expect(toast.success).toHaveBeenCalled()
  })

  it('重命名行内编辑：回车提交后调用 rename', async () => {
    mockRename.mockResolvedValue(undefined)
    renderSection()
    fireEvent.click((await screen.findAllByRole('button', { name: '重命名' }))[0]!)
    const input = await screen.findByDisplayValue('MacBook Touch ID')
    fireEvent.change(input, { target: { value: '' } })
    fireEvent.change(input, { target: { value: '办公室 Mac' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => expect(mockRename).toHaveBeenCalledWith(1, '办公室 Mac'))
  })

  it('添加成功流：create → registerVerify → toast', async () => {
    mockRegisterOptions.mockResolvedValue({
      rp: { id: 'localhost', name: '法穿' },
      user: { id: 'NDI', name: 'u1', displayName: '张三' },
      challenge: 'NDI',
      pubKeyCredParams: [{ type: 'public-key', alg: -7 }],
      excludeCredentials: [],
      authenticatorSelection: { residentKey: 'preferred' },
      attestation: 'none',
    })
    vi.mocked(navigator.credentials.create).mockResolvedValue({
      id: 'new-cred',
      rawId: encoder.encode('raw').buffer,
      type: 'public-key',
      response: {
        clientDataJSON: encoder.encode('{}').buffer,
        attestationObject: encoder.encode('att').buffer,
      },
    } as unknown as Credential)
    mockRegisterVerify.mockResolvedValue({
      id: 3,
      name: '通行密钥',
      rp_id: 'localhost',
      created_at: '2026-10-05T00:00:00Z',
      last_used_at: null,
    })

    renderSection()
    fireEvent.click(await screen.findByRole('button', { name: '添加通行密钥' }))

    await waitFor(() => {
      expect(mockRegisterVerify).toHaveBeenCalledTimes(1)
      expect(toast.success).toHaveBeenCalledWith('通行密钥已添加')
    })
  })

  it('浏览器不支持时不渲染添加入口，列表提示不支持', async () => {
    stubWebauthn(false)
    mockList.mockResolvedValue([])
    renderSection()
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: '添加通行密钥' })).toBeNull()
    })
    expect(await screen.findByText('当前浏览器不支持通行密钥')).toBeTruthy()
  })
})
