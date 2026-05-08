/**
 * Auth Feature API
 * 认证模块 API 封装 - 使用 JWT 认证
 */

import ky, { type KyInstance } from 'ky'
import { API_BASE_URL } from '@/lib/api'

import type {
  ApprovalResponse,
  LoginRequest,
  LoginResponse,
  PasswordResetConfirmRequest,
  PasswordResetOut,
  PendingUser,
  RegisterRequest,
  RegisterResponse,
  TokenPairResponse,
  TokenRefreshResponse,
  User,
} from './types'
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
  shouldRefreshToken,
} from '@/lib/token'


/**
 * 是否正在刷新 token
 */
let isRefreshing = false
let refreshPromise: Promise<string> | null = null

/**
 * 刷新 access token
 */
async function refreshAccessToken(): Promise<string> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) {
    throw new Error('No refresh token')
  }

  const response = await ky
    .post(`${API_BASE_URL}/token/refresh`, {
      json: { refresh: refreshToken },
    })
    .json<TokenRefreshResponse>()

  // 更新 access token（保留原 refresh token）
  setTokens({
    access: response.access,
    refresh: refreshToken,
  })

  return response.access
}

/**
 * 获取有效的 access token（如需要则刷新）
 */
async function getValidAccessToken(): Promise<string | null> {
  const token = getAccessToken()
  if (!token) return null

  // 检查是否需要刷新
  if (shouldRefreshToken()) {
    // 避免并发刷新
    if (isRefreshing && refreshPromise) {
      return refreshPromise
    }

    isRefreshing = true
    refreshPromise = refreshAccessToken()
      .catch(() => {
        clearTokens()
        return null
      })
      .finally(() => {
        isRefreshing = false
        refreshPromise = null
      }) as Promise<string>

    return refreshPromise
  }

  return token
}

/**
 * 创建带 JWT 认证的 Ky 实例
 */
const createAuthenticatedApi = (): KyInstance => {
  return ky.create({
    prefixUrl: API_BASE_URL,
    hooks: {
      beforeRequest: [
        async (request) => {
          const token = await getValidAccessToken()
          if (token) {
            request.headers.set('Authorization', `Bearer ${token}`)
          }
        },
      ],
      afterResponse: [
        async (request, _options, response) => {
          // 如果返回 401，尝试刷新 token 并重试
          if (response.status === 401 && !request.url.includes('/token/')) {
            try {
              const newToken = await refreshAccessToken()
              // 重试请求
              const retryRequest = new Request(request, {
                headers: new Headers(request.headers),
              })
              retryRequest.headers.set('Authorization', `Bearer ${newToken}`)
              return ky(retryRequest)
            } catch {
              clearTokens()
              throw new Error('Session expired')
            }
          }
          return response
        },
      ],
    },
  })
}

/**
 * 认证 API 实例（带 JWT）
 */
let authenticatedApi = createAuthenticatedApi()

/**
 * 重新创建 API 实例（token 更新后调用）
 */
export function resetApiInstance(): void {
  authenticatedApi = createAuthenticatedApi()
}

/**
 * 认证 API
 */
export const authApi = {
  /**
   * 用户登录
   * 1. 调用 /organization/login 验证凭证并获取用户信息
   * 2. 调用 /token/pair 获取 JWT token
   */
  login: async (data: LoginRequest): Promise<LoginResponse> => {
    // 先获取 JWT token
    const tokenResponse = await ky
      .post(`${API_BASE_URL}/token/pair`, {
        json: data,
      })
      .json<TokenPairResponse>()

    // 保存 token
    setTokens(tokenResponse)

    // 重新创建 API 实例
    resetApiInstance()

    // 获取用户信息
    const user = await authenticatedApi.get('organization/me').json<User>()

    return {
      success: true,
      user,
      access: tokenResponse.access,
      refresh: tokenResponse.refresh,
    }
  },

  /**
   * 用户登出
   */
  logout: async (): Promise<{ success: boolean }> => {
    // 清除本地 token
    clearTokens()
    resetApiInstance()
    return { success: true }
  },

  /**
   * 用户注册
   * POST /api/v1/organization/register
   * 仅负责注册，不处理自动登录（由 useRegisterMutation 处理）
   */
  register: async (data: RegisterRequest): Promise<RegisterResponse> => {
    return ky
      .post(`${API_BASE_URL}/organization/register`, {
        json: data,
      })
      .json<RegisterResponse>()
  },

  /**
   * 首位用户注册后自动登录（获取 JWT token）
   */
  autoLogin: async (username: string, password: string): Promise<void> => {
    const tokenResponse = await ky
      .post(`${API_BASE_URL}/token/pair`, {
        json: { username, password },
      })
      .json<TokenPairResponse>()

    setTokens(tokenResponse)
    resetApiInstance()
  },

  /**
   * 获取当前用户信息
   * GET /api/v1/organization/me
   */
  getCurrentUser: async (): Promise<User> => {
    return authenticatedApi.get('organization/me').json<User>()
  },

  /**
   * 获取待审批用户列表
   * GET /api/v1/organization/lawyers/pending
   */
  getPendingUsers: async (): Promise<PendingUser[]> => {
    return authenticatedApi.get('organization/lawyers/pending').json<PendingUser[]>()
  },

  /**
   * 批准用户
   * POST /api/v1/organization/lawyers/{id}/approve
   */
  approveUser: async (userId: number): Promise<ApprovalResponse> => {
    return authenticatedApi.post(`organization/lawyers/${userId}/approve`).json<ApprovalResponse>()
  },

  /**
   * 拒绝用户
   * POST /api/v1/organization/lawyers/{id}/reject
   */
  rejectUser: async (userId: number): Promise<ApprovalResponse> => {
    return authenticatedApi.post(`organization/lawyers/${userId}/reject`).json<ApprovalResponse>()
  },

  /**
   * 刷新 token
   */
  refreshToken: async (): Promise<TokenRefreshResponse> => {
    const refreshToken = getRefreshToken()
    if (!refreshToken) {
      throw new Error('No refresh token')
    }

    const response = await ky
      .post(`${API_BASE_URL}/token/refresh`, {
        json: { refresh: refreshToken },
      })
      .json<TokenRefreshResponse>()

    setTokens({
      access: response.access,
      refresh: refreshToken,
    })

    return response
  },

  /**
   * 请求密码重置（发送重置邮件）
   * POST /api/v1/organization/password-reset/request
   */
  requestPasswordReset: async (email: string): Promise<PasswordResetOut> => {
    return ky
      .post(`${API_BASE_URL}/organization/password-reset/request`, {
        json: { email },
      })
      .json<PasswordResetOut>()
  },

  /**
   * 验证密码重置 token
   * POST /api/v1/organization/password-reset/verify
   */
  verifyPasswordResetToken: async (uid: string, token: string): Promise<PasswordResetOut> => {
    return ky
      .post(`${API_BASE_URL}/organization/password-reset/verify`, {
        json: { uid, token },
      })
      .json<PasswordResetOut>()
  },

  /**
   * 确认密码重置
   * POST /api/v1/organization/password-reset/confirm
   */
  confirmPasswordReset: async (data: PasswordResetConfirmRequest): Promise<PasswordResetOut> => {
    return ky
      .post(`${API_BASE_URL}/organization/password-reset/confirm`, {
        json: data,
      })
      .json<PasswordResetOut>()
  },
}

/**
 * 获取带认证的 API 实例（供其他模块使用）
 */
export function getAuthenticatedApi(): KyInstance {
  return authenticatedApi
}

export default authApi
