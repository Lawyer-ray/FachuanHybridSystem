/**
 * token.ts 纯逻辑单测（node 环境）。
 *
 * parseJwtPayload 是私有函数（未导出），这里通过 isTokenExpired 的返回值间接
 * 覆盖其解析链路：正常三段式 / 坏输入 / 非 JSON payload / base64url-UTF8 解码
 * 各分支均以可观测行为断言。存取链路用内存版 localStorage stub。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  hasToken,
  isTokenExpired,
  setTokens,
  shouldRefreshToken,
  withAuthToken,
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

describe('withAuthToken（换下载票据，安全审计 M-2）', () => {
  it('换取票据并拼 ?ticket=（JWT 不再进 URL）', async () => {
    // mock 只打 download-ticket 模块，不走真实网络
    const mod = await import('./download-ticket')
    const spy = vi.spyOn(mod, 'withDownloadTicket').mockResolvedValue('/media/a.pdf?ticket=TK')
    try {
      await expect(withAuthToken('/media/a.pdf')).resolves.toBe('/media/a.pdf?ticket=TK')
      expect(spy).toHaveBeenCalledWith('/media/a.pdf')
    } finally {
      spy.mockRestore()
    }
  })

  it('换票失败时原样返回路径（交给后端按 403 处理）', async () => {
    const mod = await import('./download-ticket')
    const spy = vi.spyOn(mod, 'withDownloadTicket').mockResolvedValue('/api/v1/x')
    try {
      await expect(withAuthToken('/api/v1/x')).resolves.toBe('/api/v1/x')
    } finally {
      spy.mockRestore()
    }
  })
})
