// @vitest-environment jsdom
/**
 * lib/api 客户端工厂单测（jsdom：localStorage + window 可用）。
 *
 * mock 打 ky（create/post/retry 桩，捕获 ky.create 的 hooks 配置后手工驱动）
 * 与 ./token（token 存取/过期判定）。断言聚焦：beforeRequest 的 Bearer 注入、
 * 单飞刷新（并发只打一次 /token/refresh）、afterResponse 的 401 重试矩阵
 * （非 token 路径 + retryCount 0 才刷新）、getApiBaseUrl 三级回退。
 * isLeaseFresh 纯函数已由 api-lease.test.ts 覆盖，此处不重复。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const tokenMocks = vi.hoisted(() => ({
  getAccessToken: vi.fn<() => string | null>(),
  getRefreshToken: vi.fn<() => string | null>(),
  setTokens: vi.fn(),
  clearTokens: vi.fn(),
  shouldRefreshToken: vi.fn<() => boolean>(),
}))

const kyMocks = vi.hoisted(() => ({
  create: vi.fn(),
  post: vi.fn(),
  retry: vi.fn(),
}))

vi.mock('ky', () => ({ default: kyMocks }))
vi.mock('./token', () => tokenMocks)

import { API_BASE_URL, createApiClient } from './api'

const REFRESH_LEASE_KEY = 'auth:refresh-lease'
const REFRESH_DONE_KEY = 'auth:refresh-done'

/** 从 ky.create 的入参里取 hooks 配置 */
function hooksOf(index = 0) {
  const cfg = kyMocks.create.mock.calls[index]![0] as {
    hooks: {
      beforeRequest: Array<(ctx: { request: Request }) => Promise<void>>
      afterResponse: Array<(ctx: { request: Request; response: Response; retryCount: number }) => Promise<Response>>
    }
  }
  return cfg.hooks
}

/** /token/refresh 成功桩：返回新 access（可选带轮换后的新 refresh） */
function refreshSucceeds(access = 'new-acc', refresh?: string) {
  const p = Promise.resolve(refresh === undefined ? { access } : { access, refresh })
  kyMocks.post.mockImplementation(() => Object.assign(p, { json: () => p }) as never)
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  tokenMocks.getAccessToken.mockReturnValue(null)
  tokenMocks.getRefreshToken.mockReturnValue(null)
  tokenMocks.shouldRefreshToken.mockReturnValue(false)
  refreshSucceeds()
  kyMocks.create.mockImplementation(((cfg: unknown) => cfg) as never)
  kyMocks.retry.mockReturnValue({ retried: true } as never)
})

afterEach(() => {
  localStorage.clear()
})

describe('createApiClient 骨架', () => {
  it('ky.create 拿到 prefix=API_BASE_URL，默认导出 api 实例也基于同一工厂', () => {
    expect(API_BASE_URL).toBe('/api/v1')
    const client = createApiClient()
    const cfg = kyMocks.create.mock.calls.at(-1)![0] as { prefix?: string }
    expect(cfg.prefix).toBe('/api/v1')
    expect(client).toBe(cfg)
  })

  it('调用方自定义 hooks 追加在认证 hook 之后（不覆盖认证行为）', () => {
    const mineBefore = vi.fn()
    const mineAfter = vi.fn()
    createApiClient({ hooks: { beforeRequest: [mineBefore], afterResponse: [mineAfter] } })
    const hooks = hooksOf()
    expect(hooks.beforeRequest).toHaveLength(2)
    expect(hooks.beforeRequest[1]).toBe(mineBefore)
    expect(hooks.afterResponse[1]).toBe(mineAfter)
  })
})

describe('beforeRequest：Bearer 注入', () => {
  it('有效 token：Authorization 头注入', async () => {
    tokenMocks.getAccessToken.mockReturnValue('tok-1')
    createApiClient()
    const request = new Request('http://localhost/api/v1/cases')
    await hooksOf().beforeRequest[0]!({ request })
    expect(request.headers.get('Authorization')).toBe('Bearer tok-1')
    expect(kyMocks.post).not.toHaveBeenCalled()
  })

  it('无 token：不动请求头（登录前匿名请求）', async () => {
    tokenMocks.getAccessToken.mockReturnValue(null)
    createApiClient()
    const request = new Request('http://localhost/api/v1/cases')
    await hooksOf().beforeRequest[0]!({ request })
    expect(request.headers.get('Authorization')).toBeNull()
  })

  it('token 临期（shouldRefreshToken）：先刷新再注入新 token；租约写清完整', async () => {
    tokenMocks.getAccessToken.mockReturnValueOnce('old').mockReturnValueOnce('shared-acc')
    tokenMocks.getRefreshToken.mockReturnValue('ref-1')
    tokenMocks.shouldRefreshToken.mockReturnValue(true)
    createApiClient()

    const request = new Request('http://localhost/api/v1/cases')
    await hooksOf().beforeRequest[0]!({ request })

    expect(kyMocks.post).toHaveBeenCalledTimes(1)
    expect(kyMocks.post).toHaveBeenCalledWith('/api/v1/token/refresh', { json: { refresh: 'ref-1' } })
    // 后端未返回新 refresh（未开轮换）时沿用旧的
    expect(tokenMocks.setTokens).toHaveBeenCalledWith({ access: 'new-acc', refresh: 'ref-1' })
    expect(request.headers.get('Authorization')).toBe('Bearer new-acc')
    // 租约协议：刷新完成信号写入、租约键 finally 撤销
    expect(localStorage.getItem(REFRESH_DONE_KEY)).toBeTruthy()
    expect(localStorage.getItem(REFRESH_LEASE_KEY)).toBeNull()
  })

  it('轮换响应：落库后端返回的新 refresh，不再沿用已拉黑的旧 refresh（M-8）', async () => {
    tokenMocks.getAccessToken.mockReturnValueOnce('old')
    tokenMocks.getRefreshToken.mockReturnValue('ref-old')
    tokenMocks.shouldRefreshToken.mockReturnValue(true)
    refreshSucceeds('new-acc', 'ref-new')
    createApiClient()

    const request = new Request('http://localhost/api/v1/cases')
    await hooksOf().beforeRequest[0]!({ request })

    // 关键断言：必须存新 refresh。若沿用 'ref-old'，下次刷新会被后端以
    // 「Token is blacklisted」拒绝，用户静默掉线。
    expect(tokenMocks.setTokens).toHaveBeenCalledWith({ access: 'new-acc', refresh: 'ref-new' })
  })

  it('刷新失败：清空令牌、beforeRequest 静默无头（401 处理器负责跳登录）', async () => {
    tokenMocks.getAccessToken.mockReturnValue('old')
    tokenMocks.getRefreshToken.mockReturnValue('ref-1')
    tokenMocks.shouldRefreshToken.mockReturnValue(true)
    kyMocks.post.mockImplementation((() => ({
      // 惰性拒绝：json 被调用时才产生 rejected promise，避免悬挂 unhandled rejection
      json: () => Promise.reject(new Error('refresh rejected')),
    })) as never)
    createApiClient()

    const request = new Request('http://localhost/api/v1/cases')
    await hooksOf().beforeRequest[0]!({ request })

    expect(tokenMocks.clearTokens).toHaveBeenCalled()
    expect(request.headers.get('Authorization')).toBeNull()
    expect(localStorage.getItem(REFRESH_LEASE_KEY)).toBeNull()
  })

  it('其他 tab 持新鲜租约：等完成信号后共享新 token，本 tab 不发刷新', async () => {
    vi.useFakeTimers()
    try {
      localStorage.setItem(REFRESH_LEASE_KEY, String(Date.now()))
      // 等待结束后的共享结果：有 access 且不再临期
      tokenMocks.getAccessToken.mockReturnValue('shared-acc')
      tokenMocks.shouldRefreshToken.mockReturnValue(false)
      createApiClient()

      const request = new Request('http://localhost/api/v1/cases')
      const pending = hooksOf().beforeRequest[0]!({ request })
      // 3s 内没有等到别的 tab 写 done 信号（jsdom 同页 storage 事件不触发）
      await vi.advanceTimersByTimeAsync(3_000)
      await pending

      expect(kyMocks.post).not.toHaveBeenCalled()
      expect(request.headers.get('Authorization')).toBe('Bearer shared-acc')
    } finally {
      vi.useRealTimers()
    }
  })
})

describe('单飞刷新（并发 401 共享一次 /token/refresh）', () => {
  it('并发两个过期请求只刷一次', async () => {
    tokenMocks.getAccessToken.mockReturnValue('old')
    tokenMocks.getRefreshToken.mockReturnValue('ref-1')
    tokenMocks.shouldRefreshToken.mockReturnValue(true)
    createApiClient()
    const hooks = hooksOf()

    const [r1, r2] = await Promise.all([
      hooks.beforeRequest[0]!({ request: new Request('http://localhost/api/v1/a') }),
      hooks.beforeRequest[0]!({ request: new Request('http://localhost/api/v1/b') }),
    ])
    void r1
    void r2
    expect(kyMocks.post).toHaveBeenCalledTimes(1)
  })
})

describe('afterResponse：401 重试矩阵', () => {
  function responseOf(status: number) {
    return new Response(null, { status })
  }

  it('非 401 直通', async () => {
    createApiClient()
    const res = responseOf(500)
    const hooks = hooksOf()
    await expect(hooks.afterResponse[0]!({ request: new Request('http://localhost/api/v1/x'), response: res, retryCount: 0 })).resolves.toBe(res)
    expect(kyMocks.retry).not.toHaveBeenCalled()
  })

  it('401 + 非 token 路径 + retryCount 0：刷新成功 → 新 token 头重建请求并 ky.retry', async () => {
    tokenMocks.getAccessToken.mockReturnValue(null) // 刷新前无可用 access
    tokenMocks.getRefreshToken.mockReturnValue('ref-1')
    createApiClient()
    const hooks = hooksOf()

    const retried = await hooks.afterResponse[0]!({
      request: new Request('http://localhost/api/v1/cases'),
      response: responseOf(401),
      retryCount: 0,
    })

    expect(retried).toEqual({ retried: true })
    expect(kyMocks.post).toHaveBeenCalledTimes(1)
    const [retryArg] = kyMocks.retry.mock.calls[0]! as [{ request: Request }]
    expect(retryArg.request.headers.get('Authorization')).toBe('Bearer new-acc')
  })

  it('401 但刷新失败：抛 Session expired（跳转 /login 由 location 赋值承担）', async () => {
    tokenMocks.getAccessToken.mockReturnValue(null)
    tokenMocks.getRefreshToken.mockReturnValue('ref-1')
    kyMocks.post.mockImplementation((() => ({
      json: () => Promise.reject(new Error('refresh boom')),
    })) as never)
    createApiClient()
    const hooks = hooksOf()

    await expect(
      hooks.afterResponse[0]!({
        request: new Request('http://localhost/api/v1/cases'),
        response: responseOf(401),
        retryCount: 0,
      }),
    ).rejects.toThrow('Session expired')
    expect(kyMocks.retry).not.toHaveBeenCalled()
    expect(tokenMocks.clearTokens).toHaveBeenCalled()
  })

  it('token 端点自身 401：不刷新（防止刷新风暴），响应原样返回', async () => {
    createApiClient()
    const res = responseOf(401)
    const hooks = hooksOf()
    await expect(
      hooks.afterResponse[0]!({ request: new Request('http://localhost/api/v1/token/pair'), response: res, retryCount: 0 }),
    ).resolves.toBe(res)
    expect(kyMocks.post).not.toHaveBeenCalled()
  })

  it('重试后的 401（retryCount 1）：不再刷新，响应原样返回', async () => {
    createApiClient()
    const res = responseOf(401)
    const hooks = hooksOf()
    await expect(
      hooks.afterResponse[0]!({ request: new Request('http://localhost/api/v1/cases'), response: res, retryCount: 1 }),
    ).resolves.toBe(res)
    expect(kyMocks.post).not.toHaveBeenCalled()
  })
})

describe('getApiBaseUrl 三级回退（localStorage → 环境变量 → /api/v1）', () => {
  async function freshApiBaseUrl() {
    vi.resetModules()
    const mod = await import('./api')
    return mod.API_BASE_URL
  }

  it('localStorage 的 api_base_url 最优先（Native 壳注入场景）', async () => {
    localStorage.setItem('api_base_url', 'https://native.example.com')
    expect(await freshApiBaseUrl()).toBe('https://native.example.com')
  })

  it('无存储时用 VITE_API_BASE_URL，两者皆无回退 /api/v1', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://env.example.com')
    expect(await freshApiBaseUrl()).toBe('https://env.example.com')
    vi.stubEnv('VITE_API_BASE_URL', '')
    expect(await freshApiBaseUrl()).toBe('/api/v1')
    vi.unstubAllEnvs()
  })
})
