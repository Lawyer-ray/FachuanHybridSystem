/**
 * social-api 的 token 落盘行为。
 *
 * 回归：社交回调页只调 exchangeToken 换 JWT。若它不把 access/refresh 写进
 * localStorage，跳回受保护路由时 RequireAuth（只看 hasToken()）会立刻把用户
 * 打回登录页——表现为「扫码成功后闪回登录页」，且后端日志里看不到
 * /organization/me（因为压根没进主界面）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { socialAuthApi } from './social-api'

const kyMock = vi.hoisted(() => {
  const json = vi.fn()
  return {
    json,
    post: vi.fn(() => ({ json })),
    get: vi.fn(() => ({ json })),
    delete: vi.fn(() => ({ json })),
  }
})

vi.mock('ky', () => ({
  default: {
    create: () => ({
      post: kyMock.post,
      get: kyMock.get,
      delete: kyMock.delete,
    }),
  },
}))

let storage: Map<string, string>

beforeEach(() => {
  vi.clearAllMocks()
  storage = new Map<string, string>()
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => {
      return storage.get(key) ?? null
    },
    setItem: (key: string, value: string) => {
      storage.set(key, value)
    },
    removeItem: (key: string) => {
      storage.delete(key)
    },
    clear: () => {
      storage.clear()
    },
  })
})

describe('socialAuthApi.exchangeToken', () => {
  it('兑换成功后把 access / refresh 写进 localStorage', async () => {
    kyMock.json.mockResolvedValueOnce({
      success: true,
      access: 'access-token',
      refresh: 'refresh-token',
      user_id: 7,
      username: 'lawyer_a',
    })

    const res = await socialAuthApi.exchangeToken('TEMP-CODE')

    expect(res.success).toBe(true)
    expect(storage.get('access_token')).toBe('access-token')
    expect(storage.get('refresh_token')).toBe('refresh-token')
  })

  it('兑换失败不写入 token', async () => {
    kyMock.json.mockResolvedValueOnce({ success: false, message: '授权码无效或已过期' })

    const res = await socialAuthApi.exchangeToken('BAD-CODE')

    expect(res.success).toBe(false)
    expect(storage.has('access_token')).toBe(false)
    expect(storage.has('refresh_token')).toBe(false)
  })
})
