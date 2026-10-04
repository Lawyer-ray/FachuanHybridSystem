/**
 * auth store 状态流转单测（node 环境，Zustand 无需 DOM）。
 *
 * mock 只打外围副作用层：@/lib/token（token 读写）与 ./api（登录请求），
 * store 本体保持真实，验证 init 占位、login 成败迁移与 logout 清理。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getAccessTokenMock, clearTokensMock, loginMock } = vi.hoisted(() => ({
  getAccessTokenMock: vi.fn(),
  clearTokensMock: vi.fn(),
  loginMock: vi.fn(),
}))

vi.mock('@/lib/token', () => ({
  getAccessToken: getAccessTokenMock,
  clearTokens: clearTokensMock,
}))

vi.mock('./api', () => ({
  authApi: { login: loginMock },
}))

import { useAuth } from './store'

beforeEach(() => {
  vi.clearAllMocks()
  // store 是模块级单例，逐用例复位用户态（动作函数随 setState 部分合并保留）
  useAuth.setState({ user: null })
})

describe('useAuth.init', () => {
  it('无 token：保持未登录（user 为 null）', () => {
    getAccessTokenMock.mockReturnValue(null)
    useAuth.getState().init()
    expect(useAuth.getState().user).toBeNull()
  })

  it('有 token 且未登录：置占位用户（刷新页面场景，用户名稍后补拉）', () => {
    getAccessTokenMock.mockReturnValue('access-token')
    useAuth.getState().init()
    expect(useAuth.getState().user).toEqual({ id: 0, username: '' })
  })

  it('已有用户时 init 不覆盖（补拉到的用户名不会被空占位冲掉）', () => {
    getAccessTokenMock.mockReturnValue('access-token')
    useAuth.setState({ user: { id: 1, username: '王律师' } })
    useAuth.getState().init()
    expect(useAuth.getState().user).toEqual({ id: 1, username: '王律师' })
  })
})

describe('useAuth.login', () => {
  it('成功且带回用户：user 更新、返回 ok:true，入参原样下推', async () => {
    const user = { id: 1, username: '王律师' }
    loginMock.mockResolvedValue({ success: true, user })
    const res = await useAuth.getState().login('wang', 'pass')
    expect(loginMock).toHaveBeenCalledWith({ username: 'wang', password: 'pass' })
    expect(res).toEqual({ ok: true })
    expect(useAuth.getState().user).toBe(user)
  })

  it('成功但用户信息缺失：回退占位（id=0、username 为登录名）', async () => {
    loginMock.mockResolvedValue({ success: true })
    const res = await useAuth.getState().login('zhang', 'pass')
    expect(res).toEqual({ ok: true })
    expect(useAuth.getState().user).toEqual({ id: 0, username: 'zhang' })
  })

  it('失败：透传后端 message，user 不落任何态', async () => {
    loginMock.mockResolvedValue({ success: false, message: '用户名或密码错误' })
    const res = await useAuth.getState().login('wang', 'bad')
    expect(res).toEqual({ ok: false, message: '用户名或密码错误' })
    expect(useAuth.getState().user).toBeNull()
  })

  it('失败且后端无 message：兜底「登录失败」', async () => {
    loginMock.mockResolvedValue({ success: false })
    const res = await useAuth.getState().login('wang', 'bad')
    expect(res).toEqual({ ok: false, message: '登录失败' })
  })
})

describe('useAuth.logout', () => {
  it('清理本地 token 并复位 user', () => {
    useAuth.setState({ user: { id: 1, username: '王律师' } })
    useAuth.getState().logout()
    expect(clearTokensMock).toHaveBeenCalledTimes(1)
    expect(useAuth.getState().user).toBeNull()
  })
})
