/**
 * social-api 的 token 落盘行为。
 *
 * 回归：社交回调页只调 exchangeToken 换 JWT。若它不把 access/refresh 写进
 * localStorage，跳回受保护路由时 RequireAuth（只看 hasToken()）会立刻把用户
 * 打回登录页——表现为「扫码成功后闪回登录页」，且后端日志里看不到
 * /organization/me（因为压根没进主界面）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { socialAuthApi, socialBindingsApi } from './social-api'

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

describe('createSession / createBindSession 的 in-flight 去重', () => {
  it('并发 createSession 共享同一请求（StrictMode 双挂载只发一次，state 不会互相覆盖）', async () => {
    let resolveInflight: (v: unknown) => void
    kyMock.json.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveInflight = resolve
        }),
    )

    const p1 = socialAuthApi.createSession('feishu')
    const p2 = socialAuthApi.createSession('feishu')
    expect(kyMock.post).toHaveBeenCalledTimes(1) // 并发只发一次请求

    resolveInflight!({ goto: 'https://passport.feishu.cn/x?state=S1', state: 'S1', expires_in: 300 })
    const [a, b] = await Promise.all([p1, p2])
    expect(a.state).toBe('S1')
    expect(b.state).toBe('S1')

    // in-flight 结束后清除：下一次调用（用户主动刷新二维码的重新挂载）拿新 state
    kyMock.json.mockResolvedValueOnce({ goto: 'https://passport.feishu.cn/x?state=S2', state: 'S2', expires_in: 300 })
    const third = await socialAuthApi.createSession('feishu')
    expect(third.state).toBe('S2')
    expect(kyMock.post).toHaveBeenCalledTimes(2)
  })

  it('登录会话与绑定会话的去重互不影响', async () => {
    kyMock.json.mockResolvedValue({ goto: 'https://x/?state=OK', state: 'OK', expires_in: 300 })

    await Promise.all([
      socialAuthApi.createSession('feishu'),
      socialBindingsApi.createBindSession('feishu'),
    ])

    // 两个 key 各自发请求：bind 走 authed client，不吃 login 的 in-flight 缓存
    expect(kyMock.post).toHaveBeenCalledTimes(2)
  })

  it('失败后清除 in-flight：下次调用重试而不是拿到同一个 rejected promise', async () => {
    kyMock.json.mockResolvedValueOnce({ success: false, message: '该登录方式暂不可用' })
    await expect(socialAuthApi.createSession('feishu')).rejects.toThrow('该登录方式暂不可用')

    kyMock.json.mockResolvedValueOnce({ goto: 'https://x/?state=OK', state: 'OK', expires_in: 300 })
    const retry = await socialAuthApi.createSession('feishu')
    expect(retry.state).toBe('OK')
  })
})
