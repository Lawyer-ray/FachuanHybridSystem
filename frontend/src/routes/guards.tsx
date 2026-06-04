/**
 * 路由守卫组件
 *
 * Requirements:
 * - 8.5: 页面刷新时通过 /me API 恢复认证状态
 */

import { useEffect } from 'react'
import { Navigate, Outlet, useLocation, useSearchParams } from 'react-router'
import { Loader2 } from 'lucide-react'

import { useAuth } from '@/features/auth/hooks/use-auth'
import { PATHS } from './paths'

/**
 * 认证检查期间的骨架屏
 *
 * 只渲染简单背景 + 加载指示器，不渲染 Sidebar/Navbar。
 * 避免认证失败时闪现整个后台壳。
 */
function AuthLoadingSkeleton() {
  return (
    <div className="min-h-screen bg-background">
      {/* 模拟侧边栏占位 */}
      <div className="fixed left-0 top-0 h-full w-[56px] bg-[#18181b] border-r border-[#27272a]" />
      {/* 主内容区骨架 */}
      <div className="ml-[56px] flex items-center justify-center min-h-screen">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">验证登录状态...</p>
        </div>
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
 * - 认证检查期间显示骨架屏（不渲染 Sidebar/Navbar），避免认证失败时闪现后台壳
 * - 未认证时重定向到登录页
 *
 * Validates: Requirement 8.5
 */
export function AuthGuard() {
  const { isAuthenticated, isLoading, checkAuth } = useAuth()
  const location = useLocation()

  // 页面加载时检查认证状态
  useEffect(() => {
    checkAuth()
  }, [checkAuth])

  // 加载中显示骨架屏，避免认证失败时闪现整个后台壳
  if (isLoading) {
    return <AuthLoadingSkeleton />
  }

  if (!isAuthenticated) {
    const redirectTo = location.pathname + location.search
    return <Navigate to={`${PATHS.LOGIN}?redirect=${encodeURIComponent(redirectTo)}`} replace />
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
  const [searchParams] = useSearchParams()

  // 页面加载时检查认证状态
  useEffect(() => {
    checkAuth()
  }, [checkAuth])

  // 加载中显示骨架屏
  if (isLoading) {
    return <AuthLoadingSkeleton />
  }

  // 已认证则重定向：优先跳回 redirect 参数指定的页面
  if (isAuthenticated) {
    const redirect = searchParams.get('redirect')
    return <Navigate to={redirect || PATHS.ADMIN_DASHBOARD} replace />
  }

  return <Outlet />
}
