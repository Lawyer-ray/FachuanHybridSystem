/**
 * token.ts 纯逻辑单测（node 环境）。
 *
 * parseJwtPayload 是私有函数（未导出），这里通过 isTokenExpired 的返回值间接
 * 覆盖其解析链路：正常三段式 / 坏输入 / 非 JSON payload / base64url-UTF8 解码
 * 各分支均以可观测行为断言。存取链路用内存版 localStorage stub。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { withAuthToken,
  clearTokens,
  getAccessToken,
  getRefreshToken,
  hasToken,
  isTokenExpired,
  setTokens,
  shouldRefreshToken,
} from './token'

function b64url(input: unknown): string {
  const raw = typeof input === 'string' ? input : JSON.stringify(input)
  return Buffer.from(raw, 'utf-8').toString('base64url')
}

function makeJwt(payload: Record<string, unknown>): string {
  return `${b64url({ alg: 'HS256', typ: 'JWT' })}.${b64url(payload)}.sig`
}

let storage: Map<string, string>

beforeEach(() => {
  vi.clearAllMocks()
  storage = new Map()
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => storage.get(key) ?? null,
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

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('isTokenExpired（经私有 parseJwtPayload 间接覆盖解析链路）', () => {
  it('未过期 token → false', () => {
    const exp = Math.floor(Date.now() / 1000) + 3600
    expect(isTokenExpired(makeJwt({ exp, sub: 'lawyer-1' }))).toBe(false)
  })

  it('已过期 token → true', () => {
    const exp = Math.floor(Date.now() / 1000) - 3600
    expect(isTokenExpired(makeJwt({ exp }))).toBe(true)
  })

  it('30 秒提前量：exp 距今不足 30 秒视为已过期', () => {
    const exp = Math.floor(Date.now() / 1000) + 29
    expect(isTokenExpired(makeJwt({ exp }))).toBe(true)
  })

  it('exp 距今超过 30 秒不视为过期', () => {
    const exp = Math.floor(Date.now() / 1000) + 31
    expect(isTokenExpired(makeJwt({ exp }))).toBe(false)
  })

  it('payload 含中文等多字节字符仍能解析（base64url → UTF-8 解码链路）', () => {
    const exp = Math.floor(Date.now() / 1000) + 3600
    expect(isTokenExpired(makeJwt({ exp, real_name: '张三律师', org: '北京分所' }))).toBe(false)
  })

  it('无 exp 字段 → true', () => {
    expect(isTokenExpired(makeJwt({ sub: 'lawyer-1' }))).toBe(true)
  })

  it('exp 为字符串而非 number → true', () => {
    const exp = String(Math.floor(Date.now() / 1000) + 3600)
    expect(isTokenExpired(makeJwt({ exp }))).toBe(true)
  })

  it('非三段式坏 token → true（parseJwtPayload 取不到第二段返回 null）', () => {
    expect(isTokenExpired('not-a-jwt')).toBe(true)
    expect(isTokenExpired('')).toBe(true)
    expect(isTokenExpired('a.b.c.d.e')).toBe(true) // 多段：split[1] 非法 base64 → 解码抛错被吞
  })

  it('三段式但 payload 非 JSON → true（JSON.parse 抛错被吞为 null）', () => {
    const token = `${b64url({ alg: 'HS256' })}.${b64url('this is not json {')}.sig`
    expect(isTokenExpired(token)).toBe(true)
  })
})

describe('token 存取链路（stub localStorage）', () => {
  it('setTokens 后 getAccessToken / getRefreshToken 可读回', () => {
    setTokens({ access: 'access-token', refresh: 'refresh-token' })
    expect(getAccessToken()).toBe('access-token')
    expect(getRefreshToken()).toBe('refresh-token')
    expect(hasToken()).toBe(true)
  })

  it('clearTokens 后 token 清空、hasToken 为 false', () => {
    setTokens({ access: 'access-token', refresh: 'refresh-token' })
    clearTokens()
    expect(getAccessToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
    expect(hasToken()).toBe(false)
  })

  it('shouldRefreshToken：无 token → false', () => {
    expect(shouldRefreshToken()).toBe(false)
  })

  it('shouldRefreshToken：token 未过期 → false', () => {
    const exp = Math.floor(Date.now() / 1000) + 3600
    setTokens({ access: makeJwt({ exp }), refresh: 'r' })
    expect(shouldRefreshToken()).toBe(false)
  })

  it('shouldRefreshToken：token 已过期 → true', () => {
    const exp = Math.floor(Date.now() / 1000) - 3600
    setTokens({ access: makeJwt({ exp }), refresh: 'r' })
    expect(shouldRefreshToken()).toBe(true)
  })
})

describe('withAuthToken（裸链接拼 ?token=）', () => {
  it('有 token 时拼接且复用已有查询参数的分隔符', () => {
    vi.stubGlobal('localStorage', {
      getItem: (k: string) => (k === 'access_token' ? 'tok en+1' : null),
      setItem: () => {},
      removeItem: () => {},
      clear: () => {},
    })
    try {
      expect(withAuthToken('/media/a.pdf')).toBe('/media/a.pdf?token=tok%20en%2B1')
      expect(withAuthToken('/api/v1/x?y=1')).toBe('/api/v1/x?y=1&token=tok%20en%2B1')
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('无 token 原样返回（session 登录态交给 cookie）', () => {
    vi.stubGlobal('localStorage', {
      getItem: () => null,
      setItem: () => {},
      removeItem: () => {},
      clear: () => {},
    })
    try {
      expect(withAuthToken('/media/a.pdf')).toBe('/media/a.pdf')
    } finally {
      vi.unstubAllGlobals()
    }
  })
})
