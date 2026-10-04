/**
 * auth/api 单测（node 环境）。
 *
 * mock 打 ky（HTTPError 形状桩）、@/lib/api（默认客户端）、@/lib/token（setTokens）。
 * 断言聚焦：登录错误分级（401 → 密码文案 / 其他 → errMessage 通道）、
 * token 落库、me 接口失败不阻塞登录成功。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

/** 与被测代码 `e instanceof HTTPError` 判定一致的错误形状（ky 桩，需 hoisted：mock 工厂引用） */
const { FakeHTTPError } = vi.hoisted(() => {
  class FakeHTTPError extends Error {
    response: { status: number }
    constructor(status: number, message = `Request failed with status code ${status}`) {
      super(message)
      this.name = 'HTTPError'
      this.response = { status }
    }
  }
  return { FakeHTTPError }
})

const kyPost = vi.fn()
const meGet = vi.fn()

vi.mock('ky', () => ({
  HTTPError: FakeHTTPError,
  default: { post: (...args: unknown[]) => kyPost(...(args as [])) },
}))

vi.mock('@/lib/api', () => ({
  api: { get: (...args: unknown[]) => meGet(...(args as [])) },
  API_BASE_URL: '/api/v1',
}))

vi.mock('@/lib/token', () => ({
  setTokens: vi.fn(),
}))

import { setTokens } from '@/lib/token'
import { authApi } from './api'

function tokenResponse() {
  const p = Promise.resolve({ access: 'acc-1', refresh: 'ref-1', username: 'lawyer' })
  return Object.assign(p, { json: () => p })
}

/** ky 桩的失败形状：.json() 拒绝（被测代码 await ky.post(...).json()） */
function jsonReject(err: Error) {
  return { json: () => Promise.reject(err) }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('authApi.login（错误分级）', () => {
  it('成功：token pair 落库、拉取 organization/me 返回用户', async () => {
    kyPost.mockReturnValueOnce(tokenResponse())
    const mePromise = Promise.resolve({ id: 1, username: 'lawyer', display_name: '李律师' })
    meGet.mockReturnValueOnce(Object.assign(mePromise, { json: () => mePromise }))

    const res = await authApi.login({ username: 'lawyer', password: 'x' })

    expect(kyPost).toHaveBeenCalledWith('/api/v1/token/pair', { json: { username: 'lawyer', password: 'x' } })
    // 后端响应含 username 冗余字段，落库对象按 TokenPair 超集直传
    expect(setTokens).toHaveBeenCalledWith(expect.objectContaining({ access: 'acc-1', refresh: 'ref-1' }))
    expect(meGet).toHaveBeenCalledWith('organization/me')
    expect(res.success).toBe(true)
    expect(res.user).toEqual({ id: 1, username: 'lawyer', display_name: '李律师' })
  })

  it('401 → 「用户名或密码错误」，不落 token', async () => {
    kyPost.mockReturnValueOnce(jsonReject(new FakeHTTPError(401)))
    const res = await authApi.login({ username: 'u', password: 'x' })
    expect(res).toEqual({ success: false, message: '用户名或密码错误' })
    expect(setTokens).not.toHaveBeenCalled()
  })

  it('500 / 断网等非 401 → 走 errMessage 通道（HTTPError 无 data → fallback 文案）', async () => {
    kyPost.mockReturnValueOnce(jsonReject(new FakeHTTPError(500)))
    const res = await authApi.login({ username: 'u', password: 'p' })
    expect(res).toEqual({ success: false, message: '登录失败，请检查网络后重试' })
  })

  it('超时（ky TimeoutError，无 data）→ 超时文案', async () => {
    const err = new Error('Timeout')
    err.name = 'TimeoutError'
    kyPost.mockReturnValueOnce(jsonReject(err))
    const res = await authApi.login({ username: 'u', password: 'p' })
    expect(res).toEqual({ success: false, message: '请求超时，请稍后重试' })
  })

  it('me 接口失败不阻塞登录：success:true、user 缺省', async () => {
    kyPost.mockReturnValueOnce(tokenResponse())
    meGet.mockReturnValueOnce(jsonReject(new FakeHTTPError(500)))
    const res = await authApi.login({ username: 'u', password: 'p' })
    expect(res.success).toBe(true)
    expect(res.user).toBeUndefined()
  })
})
