vi.mock('ky', () => {
  const mockPost = vi.fn().mockReturnValue({
    json: vi.fn().mockResolvedValue({}),
  })
  return {
    default: {
      post: mockPost,
    },
  }
})

vi.mock('@/lib/api', () => ({
  api: {
    get: vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue({}) }),
    post: vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue({}) }),
  },
  API_BASE_URL: 'http://localhost:8002/api/v1',
}))

vi.mock('@/lib/token', () => ({
  clearTokens: vi.fn(),
  getRefreshToken: vi.fn().mockReturnValue('refresh-token'),
  setTokens: vi.fn(),
}))

import { authApi } from '../api'
import ky from 'ky'
import { api } from '@/lib/api'
import { setTokens, clearTokens, getRefreshToken } from '@/lib/token'

describe('authApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('login posts credentials, sets tokens, fetches user', async () => {
    const mockTokenResponse = { access: 'acc', refresh: 'ref' }
    const mockUser = { id: 1, username: 'test' }
    ;(ky.post as ReturnType<typeof vi.fn>).mockReturnValueOnce({
      json: vi.fn().mockResolvedValue(mockTokenResponse),
    })
    ;(api.get as ReturnType<typeof vi.fn>).mockReturnValueOnce({
      json: vi.fn().mockResolvedValue(mockUser),
    })

    const result = await authApi.login({ username: 'test', password: 'pass' })

    expect(setTokens).toHaveBeenCalledWith(mockTokenResponse)
    expect(result.success).toBe(true)
    expect(result.user).toEqual(mockUser)
  })

  it('logout clears tokens and returns success', async () => {
    const result = await authApi.logout()
    expect(clearTokens).toHaveBeenCalled()
    expect(result).toEqual({ success: true })
  })

  it('register posts registration data', async () => {
    const mockResponse = { success: true, requires_approval: true, message: 'ok' }
    ;(ky.post as ReturnType<typeof vi.fn>).mockReturnValueOnce({
      json: vi.fn().mockResolvedValue(mockResponse),
    })

    const result = await authApi.register({ username: 'newuser', password: 'pass' })
    expect(result).toEqual(mockResponse)
  })

  it('autoLogin posts credentials and sets tokens', async () => {
    const mockTokenResponse = { access: 'new-acc', refresh: 'new-ref' }
    ;(ky.post as ReturnType<typeof vi.fn>).mockReturnValueOnce({
      json: vi.fn().mockResolvedValue(mockTokenResponse),
    })

    await authApi.autoLogin('user', 'pass')
    expect(setTokens).toHaveBeenCalledWith(mockTokenResponse)
  })

  it('getCurrentUser fetches user info', async () => {
    const mockUser = { id: 1, username: 'test' }
    ;(api.get as ReturnType<typeof vi.fn>).mockReturnValueOnce({
      json: vi.fn().mockResolvedValue(mockUser),
    })

    const result = await authApi.getCurrentUser()
    expect(result).toEqual(mockUser)
  })

  it('getPendingUsers fetches pending list', async () => {
    const mockList = [{ id: 1, username: 'pending' }]
    ;(api.get as ReturnType<typeof vi.fn>).mockReturnValueOnce({
      json: vi.fn().mockResolvedValue(mockList),
    })

    const result = await authApi.getPendingUsers()
    expect(result).toEqual(mockList)
  })

  it('approveUser posts approval', async () => {
    const mockResult = { success: true, message: 'approved' }
    ;(api.post as ReturnType<typeof vi.fn>).mockReturnValueOnce({
      json: vi.fn().mockResolvedValue(mockResult),
    })

    const result = await authApi.approveUser(1)
    expect(result).toEqual(mockResult)
  })

  it('rejectUser posts rejection', async () => {
    const mockResult = { success: true, message: 'rejected' }
    ;(api.post as ReturnType<typeof vi.fn>).mockReturnValueOnce({
      json: vi.fn().mockResolvedValue(mockResult),
    })

    const result = await authApi.rejectUser(1)
    expect(result).toEqual(mockResult)
  })

  it('refreshToken throws when no refresh token', async () => {
    ;(getRefreshToken as ReturnType<typeof vi.fn>).mockReturnValueOnce(null)
    await expect(authApi.refreshToken()).rejects.toThrow('No refresh token')
  })

  it('refreshToken refreshes and sets tokens', async () => {
    const mockResponse = { access: 'new-access' }
    ;(ky.post as ReturnType<typeof vi.fn>).mockReturnValueOnce({
      json: vi.fn().mockResolvedValue(mockResponse),
    })

    const result = await authApi.refreshToken()
    expect(setTokens).toHaveBeenCalledWith({ access: 'new-access', refresh: 'refresh-token' })
    expect(result).toEqual(mockResponse)
  })

  it('requestPasswordReset sends email', async () => {
    const mockResult = { success: true, message: 'sent' }
    ;(ky.post as ReturnType<typeof vi.fn>).mockReturnValueOnce({
      json: vi.fn().mockResolvedValue(mockResult),
    })

    const result = await authApi.requestPasswordReset('test@example.com')
    expect(result).toEqual(mockResult)
  })

  it('verifyPasswordResetToken sends uid and token', async () => {
    const mockResult = { success: true, data: { is_valid: true } }
    ;(ky.post as ReturnType<typeof vi.fn>).mockReturnValueOnce({
      json: vi.fn().mockResolvedValue(mockResult),
    })

    const result = await authApi.verifyPasswordResetToken('uid', 'token')
    expect(result).toEqual(mockResult)
  })

  it('confirmPasswordReset sends reset data', async () => {
    const mockResult = { success: true, message: 'reset' }
    ;(ky.post as ReturnType<typeof vi.fn>).mockReturnValueOnce({
      json: vi.fn().mockResolvedValue(mockResult),
    })

    const result = await authApi.confirmPasswordReset({
      uid: 'uid',
      token: 'token',
      new_password: 'new',
      confirm_password: 'new',
    })
    expect(result).toEqual(mockResult)
  })
})
