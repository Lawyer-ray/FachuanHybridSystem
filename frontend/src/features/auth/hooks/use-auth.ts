/**
 * useAuth Hook
 * 封装认证状态访问
 *
 * Requirements:
 * - 8.1: 存储当前用户信息和认证状态
 * - 8.4: 提供 isAuthenticated 和 isAdmin 计算属性
 */

import {
  useAuthStore,
  selectUser,
  selectIsAuthenticated,
  selectIsAdmin,
  selectIsLoading,
} from '@/stores/auth'

/**
 * 认证状态 Hook
 *
 * 提供统一的认证状态访问接口，封装 Zustand store 的使用细节。
 * 组件可以通过此 hook 获取用户信息、认证状态和认证操作。
 *
 * @example
 * ```tsx
 * function UserProfile() {
 *   const { user, isAuthenticated, isAdmin, logout } = useAuth()
 *
 *   if (!isAuthenticated) {
 *     return <Navigate to="/login" />
 *   }
 *
 *   return (
 *     <div>
 *       <p>欢迎, {user?.real_name}</p>
 *       {isAdmin && <AdminPanel />}
 *       <button onClick={logout}>登出</button>
 *     </div>
 *   )
 * }
 * ```
 *
 * @returns 认证状态和操作
 */
export function useAuth() {
  // 使用选择器获取状态，避免不必要的重渲染
  const user = useAuthStore(selectUser)
  const isAuthenticated = useAuthStore(selectIsAuthenticated)
  const isAdmin = useAuthStore(selectIsAdmin)
  const isLoading = useAuthStore(selectIsLoading)

  // 获取 actions
  const login = useAuthStore((state) => state.login)
  const logout = useAuthStore((state) => state.logout)
  const checkAuth = useAuthStore((state) => state.checkAuth)

  return {
    /** 当前用户信息，未登录时为 null */
    user,
    /** 是否已认证 */
    isAuthenticated,
    /** 是否为管理员 */
    isAdmin,
    /** 是否正在加载认证状态 */
    isLoading,
    /** 登录操作 - 设置用户信息并更新认证状态 */
    login,
    /** 登出操作 - 清除用户信息和认证状态 */
    logout,
    /** 检查认证状态 - 通过 /me API 恢复认证状态 */
    checkAuth,
  }
}

export default useAuth
