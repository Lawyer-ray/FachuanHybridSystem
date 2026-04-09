/**
 * 路由守卫组件
 *
 * Requirements:
 * - 8.5: 页面刷新时通过 /me API 恢复认证状态
 */

import { useEffect } from 'react'
import { Navigate, Outlet } from 'react-router'
import { Loader2 } from 'lucide-react'

import { useAuth } from '@/features/auth/hooks/use-auth'
import { PATHS } from './paths'

/**
 * 加载状态组件
 * 在认证状态检查期间显示
 */
function LoadingSpinner() {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">验证登录状态...</p>
      </div>
    </div>
  )
}

/**
 * 认证守卫 - 需要登录才能访问
 * 未登录用户将被重定向到登录页面
 *
 * 功能：
 * - 页面加载时调用 checkAuth 恢复认证状态
 * - 加载期间显示 loading 状态
 * - 未认证时重定向到登录页
 *
 * Validates: Requirement 8.5
 */
export function AuthGuard() {
  const { isAuthenticated, isLoading, checkAuth } = useAuth()

  // 页面加载时检查认证状态
  useEffect(() => {
    checkAuth()
  }, [checkAuth])

  // 加载中显示 loading 状态
  if (isLoading) {
    return <LoadingSpinner />
  }

  // 未认证则重定向到登录页
  if (!isAuthenticated) {
    return <Navigate to={PATHS.LOGIN} replace />
  }

  return <Outlet />
}

/**
 * 访客守卫 - 已登录用户将被重定向到 dashboard
 * 用于登录、注册等页面，防止已登录用户访问
 *
 * 功能：
 * - 页面加载时调用 checkAuth 恢复认证状态
 * - 加载期间显示 loading 状态
 * - 已认证时重定向到 dashboard
 *
 * Validates: Requirement 8.5
 */
export function GuestGuard() {
  const { isAuthenticated, isLoading, checkAuth } = useAuth()

  // 页面加载时检查认证状态
  useEffect(() => {
    checkAuth()
  }, [checkAuth])

  // 加载中显示 loading 状态
  if (isLoading) {
    return <LoadingSpinner />
  }

  // 已认证则重定向到 dashboard
  if (isAuthenticated) {
    return <Navigate to={PATHS.ADMIN_DASHBOARD} replace />
  }

  return <Outlet />
}
