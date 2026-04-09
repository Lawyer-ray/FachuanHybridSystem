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
export const useAuthStore = create<AuthState>((set) => {
  let checkPromise: Promise<void> | null = null

  return {
  // 初始状态 — isLoading 默认 true，防止 AuthGuard 首次渲染时因 isAuthenticated=false 直接跳转登录页
  user: null,
  isAuthenticated: false,
  isLoading: true,

  setUser: (user: User | null) => {
    set({
      user,
      isAuthenticated: user !== null && user.is_active,
    })
  },

  login: (user: User) => {
    set({
      user,
      isAuthenticated: true,
      isLoading: false,
    })
  },

  logout: () => {
    clearTokens()
    checkPromise = null
    set({
      user: null,
      isAuthenticated: false,
      isLoading: false,
    })
  },

  checkAuth: async () => {
    // 避免重复请求
    if (checkPromise) {
      return checkPromise
    }

    // 如果没有 token，直接返回未认证状态
    if (!hasToken()) {
      set({ user: null, isAuthenticated: false, isLoading: false })
      return
    }

    set({ isLoading: true })

    checkPromise = authApi.getCurrentUser()
      .then((user) => {
        set({ user, isAuthenticated: true, isLoading: false })
      })
      .catch(() => {
        clearTokens()
        set({ user: null, isAuthenticated: false, isLoading: false })
      })

    return checkPromise
  },
  }
})

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
