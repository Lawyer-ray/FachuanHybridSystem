/**
 * Auth Store
 * 认证状态管理 (Zustand) - JWT 版本
 *
 * Requirements:
 * - 8.1: 存储当前用户信息和认证状态
 * - 8.2: 用户登录成功时更新认证状态为已登录
 * - 8.3: 用户登出时清除用户信息和认证状态
 * - 8.4: 提供 isAuthenticated 和 isAdmin 计算属性
 * - 8.5: 页面刷新时通过 token 和 /me API 恢复认证状态
 */

import { create } from 'zustand'

import { authApi } from '@/features/auth/api'
import type { User } from '@/features/auth/types'
import { clearTokens, hasToken } from '@/lib/token'

/**
 * 认证状态接口
 */
interface AuthState {
  /** 当前用户信息 */
  user: User | null
  /** 是否已认证 */
  isAuthenticated: boolean
  /** 是否正在加载 */
  isLoading: boolean

  // Actions
  /** 设置用户信息 */
  setUser: (user: User | null) => void
  /** 登录 - 设置用户并更新认证状态 */
  login: (user: User) => void
  /** 登出 - 清除用户信息、token 和认证状态 */
  logout: () => void
  /** 检查认证状态 - 通过 token 和 /me API 恢复认证状态 */
  checkAuth: () => Promise<void>
}

/**
 * 认证状态 Store
 *
 * 使用 Zustand 管理全局认证状态，包括：
 * - 用户信息存储
 * - 认证状态管理
 * - 登录/登出操作
 * - 页面刷新时的状态恢复
 */
export const useAuthStore = create<AuthState>((set, get) => ({
  // 初始状态
  user: null,
  isAuthenticated: false,
  isLoading: false,

  /**
   * 设置用户信息
   * @param user - 用户信息或 null
   */
  setUser: (user: User | null) => {
    set({
      user,
      isAuthenticated: user !== null && user.is_active,
    })
  },

  /**
   * 登录操作
   * 设置用户信息并更新认证状态为已登录
   *
   * Validates: Requirement 8.2
   * @param user - 登录成功后的用户信息
   */
  login: (user: User) => {
    set({
      user,
      isAuthenticated: true,
      isLoading: false,
    })
  },

  /**
   * 登出操作
   * 清除用户信息、token 和认证状态
   *
   * Validates: Requirement 8.3
   */
  logout: () => {
    clearTokens()
    set({
      user: null,
      isAuthenticated: false,
      isLoading: false,
    })
  },

  /**
   * 检查认证状态
   * 通过检查 token 和调用 /me API 恢复认证状态
   * 用于页面刷新时恢复用户会话
   *
   * Validates: Requirement 8.5
   */
  checkAuth: async () => {
    // 避免重复检查
    if (get().isLoading) {
      return
    }

    // 如果没有 token，直接返回未认证状态
    if (!hasToken()) {
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
      })
      return
    }

    set({ isLoading: true })

    try {
      const user = await authApi.getCurrentUser()
      set({
        user,
        isAuthenticated: true,
        isLoading: false,
      })
    } catch {
      // token 无效或过期，清除状态
      clearTokens()
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
      })
    }
  },
}))

/**
 * 计算属性：是否为管理员
 * 从 store 中获取用户的 is_admin 状态
 *
 * Validates: Requirement 8.4
 *
 * @example
 * ```tsx
 * const isAdmin = useAuthStore(selectIsAdmin)
 * ```
 */
export const selectIsAdmin = (state: AuthState): boolean => {
  return state.user?.is_admin ?? false
}

/**
 * 计算属性：是否已认证
 *
 * Validates: Requirement 8.4
 *
 * @example
 * ```tsx
 * const isAuthenticated = useAuthStore(selectIsAuthenticated)
 * ```
 */
export const selectIsAuthenticated = (state: AuthState): boolean => {
  return state.isAuthenticated
}

/**
 * 计算属性：当前用户
 *
 * @example
 * ```tsx
 * const user = useAuthStore(selectUser)
 * ```
 */
export const selectUser = (state: AuthState): User | null => {
  return state.user
}

/**
 * 计算属性：是否正在加载
 *
 * @example
 * ```tsx
 * const isLoading = useAuthStore(selectIsLoading)
 * ```
 */
export const selectIsLoading = (state: AuthState): boolean => {
  return state.isLoading
}

export default useAuthStore
