/**
 * Auth Feature API
 * 认证模块 API 封装 - 使用 JWT 认证
 */

import ky from 'ky'
import { api, API_BASE_URL } from '@/lib/api'

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
  getRefreshToken,
  setTokens,
} from '@/lib/token'

/**
 * 认证 API
 */
export const authApi = {
  /**
   * 用户登录
   */
  login: async (data: LoginRequest): Promise<LoginResponse> => {
    const tokenResponse = await ky
      .post(`${API_BASE_URL}/token/pair`, {
        json: data,
      })
      .json<TokenPairResponse>()

    setTokens(tokenResponse)

    // lib/api.ts 的 beforeRequest 每次请求自动读取最新 token，无需 resetApiInstance
    const user = await api.get('organization/me').json<User>()

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
    clearTokens()
    return { success: true }
  },

  /**
   * 用户注册
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
  },

  /**
   * 获取当前用户信息
   */
  getCurrentUser: async (): Promise<User> => {
    return api.get('organization/me').json<User>()
  },

  /**
   * 获取待审批用户列表
   */
  getPendingUsers: async (): Promise<PendingUser[]> => {
    return api.get('organization/lawyers/pending').json<PendingUser[]>()
  },

  /**
   * 批准用户
   */
  approveUser: async (userId: number): Promise<ApprovalResponse> => {
    return api.post(`organization/lawyers/${userId}/approve`).json<ApprovalResponse>()
  },

  /**
   * 拒绝用户
   */
  rejectUser: async (userId: number): Promise<ApprovalResponse> => {
    return api.post(`organization/lawyers/${userId}/reject`).json<ApprovalResponse>()
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
   */
  confirmPasswordReset: async (data: PasswordResetConfirmRequest): Promise<PasswordResetOut> => {
    return ky
      .post(`${API_BASE_URL}/organization/password-reset/confirm`, {
        json: data,
      })
      .json<PasswordResetOut>()
  },
}

export default authApi
