/**
 * passkey-api 契约测试（node 环境）。
 *
 * 后端业务失败一律 HTTP 200 + { success: false, message }，API 层负责 throw；
 * 这条约定若被破坏，调用方会拿到「成功但无数据」的静默失败，故逐端点锁定。
 * 同时校验登录验证成功后 token 落库（与 exchangeToken 同一约定）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const clientMock = vi.hoisted(() => ({
  post: vi.fn(),
  get: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}))
const setTokensMock = vi.hoisted(() => vi.fn())

vi.mock('ky', async (importOriginal) => {
  const actual = await importOriginal<typeof import('ky')>()
  return { ...actual, default: { create: () => clientMock } }
})
vi.mock('@/lib/api', () => ({ createApiClient: () => clientMock }))
vi.mock('@/lib/token', () => ({ setTokens: setTokensMock }))

import { passkeyApi } from './passkey-api'

/** 让 mock 返回链式 .json()：ky 的响应是 thenable + .json()，
 *  这里直接返回带 json 方法的对象即可满足被测代码的写法 */
function chain<T>(value: T) {
  return { json: () => Promise.resolve(value) }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('passkeyApi.loginOptions', () => {
  it('成功：返回 public_key', async () => {
    clientMock.post.mockReturnValue(
      chain({ success: true, message: '', public_key: { challenge: 'abc' } }),
    )
    const r = await passkeyApi.loginOptions()
    expect(clientMock.post).toHaveBeenCalledWith('/api/v1/social/passkey/login/options')
    expect(r).toEqual({ challenge: 'abc' })
  })

  it('public_key 为 null 时返回空对象（不抛错）', async () => {
    clientMock.post.mockReturnValue(chain({ success: true, message: '', public_key: null }))
    expect(await passkeyApi.loginOptions()).toEqual({})
  })

  it('success=false：抛后端 message', async () => {
    clientMock.post.mockReturnValue(chain({ success: false, message: '不支持通行密钥', public_key: null }))
    await expect(passkeyApi.loginOptions()).rejects.toThrow('不支持通行密钥')
  })

  it('success=false 且无 message：抛 fallback', async () => {
    clientMock.post.mockReturnValue(chain({ success: false, message: '', public_key: null }))
    await expect(passkeyApi.loginOptions()).rejects.toThrow('通行密钥暂不可用')
  })
})

describe('passkeyApi.loginVerify', () => {
  it('成功且含 token：落库并返回', async () => {
    const data = { success: true, access: 'A', refresh: 'R', user_id: 1, username: 'u' }
    clientMock.post.mockReturnValue(chain(data))

    const r = await passkeyApi.loginVerify({ id: 'x' } as never)
    expect(clientMock.post).toHaveBeenCalledWith('/api/v1/social/passkey/login/verify', {
      json: { credential: { id: 'x' } },
    })
    expect(setTokensMock).toHaveBeenCalledWith({ access: 'A', refresh: 'R' })
    expect(r).toBe(data)
  })

  it('失败：不落 token，原样返回给调用方判断', async () => {
    const data = { success: false, message: '验证失败' }
    clientMock.post.mockReturnValue(chain(data))

    const r = await passkeyApi.loginVerify({ id: 'x' } as never)
    expect(setTokensMock).not.toHaveBeenCalled()
    expect(r).toBe(data)
  })

  it('success 为真但缺 token：不落库（防空值覆盖）', async () => {
    clientMock.post.mockReturnValue(chain({ success: true }))
    await passkeyApi.loginVerify({ id: 'x' } as never)
    expect(setTokensMock).not.toHaveBeenCalled()
  })
})

describe('passkeyApi.registerOptions', () => {
  it('成功：返回 public_key', async () => {
    clientMock.post.mockReturnValue(
      chain({ success: true, message: '', public_key: { rp: { id: 'l' } } }),
    )
    expect(await passkeyApi.registerOptions()).toEqual({ rp: { id: 'l' } })
  })

  it('失败抛后端 message', async () => {
    clientMock.post.mockReturnValue(chain({ success: false, message: '已达上限', public_key: null }))
    await expect(passkeyApi.registerOptions()).rejects.toThrow('已达上限')
  })
})

describe('passkeyApi.registerVerify', () => {
  it('成功返回凭据行', async () => {
    const cred = { id: 1, name: 'Mac', rp_id: 'x', created_at: '', last_used_at: null }
    clientMock.post.mockReturnValue(chain({ success: true, message: '', credential: cred }))
    expect(await passkeyApi.registerVerify({ id: 'x' } as never)).toBe(cred)
  })

  it('success=false 抛错', async () => {
    clientMock.post.mockReturnValue(chain({ success: false, message: '注册被拒', credential: null }))
    await expect(passkeyApi.registerVerify({ id: 'x' } as never)).rejects.toThrow('注册被拒')
  })

  it('success 真但 credential 缺省：抛错（不返回 null）', async () => {
    clientMock.post.mockReturnValue(chain({ success: true, message: '' }))
    await expect(passkeyApi.registerVerify({ id: 'x' } as never)).rejects.toThrow('通行密钥注册失败')
  })
})

describe('passkeyApi.list', () => {
  it('返回凭据数组', async () => {
    clientMock.get.mockReturnValue(chain({ credentials: [{ id: 1 }] }))
    expect(await passkeyApi.list()).toEqual([{ id: 1 }])
  })

  it('credentials 缺省时返回空数组', async () => {
    clientMock.get.mockReturnValue(chain({}))
    expect(await passkeyApi.list()).toEqual([])
  })
})

describe('passkeyApi.rename / remove', () => {
  it('rename 成功不抛错', async () => {
    clientMock.patch.mockReturnValue(chain({ success: true, message: '' }))
    await expect(passkeyApi.rename(3, '新名')).resolves.toBeUndefined()
    expect(clientMock.patch).toHaveBeenCalledWith('social/passkey/credentials/3', { json: { name: '新名' } })
  })

  it('rename 失败抛后端 message', async () => {
    clientMock.patch.mockReturnValue(chain({ success: false, message: '名称过长' }))
    await expect(passkeyApi.rename(3, 'x')).rejects.toThrow('名称过长')
  })

  it('remove 成功不抛错', async () => {
    clientMock.delete.mockReturnValue(chain({ success: true, message: '' }))
    await expect(passkeyApi.remove(5)).resolves.toBeUndefined()
    expect(clientMock.delete).toHaveBeenCalledWith('social/passkey/credentials/5')
  })

  it('remove 失败抛 fallback', async () => {
    clientMock.delete.mockReturnValue(chain({ success: false, message: '' }))
    await expect(passkeyApi.remove(5)).rejects.toThrow('删除失败')
  })
})
