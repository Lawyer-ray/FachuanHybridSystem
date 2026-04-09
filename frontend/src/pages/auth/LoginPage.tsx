/**
 * LoginPage - 登录页面
 *
 * 集成 LoginForm 和 AuthLayoutCard，实现完整的登录功能。
 *
 * @validates Requirements 5.5 - 登录成功跳转到 /dashboard 页面
 * @validates Requirements 5.6 - 提供跳转到注册页面的链接
 * @validates Requirements 5.7 - 支持明暗主题切换（通过 AuthLayout 实现）
 */

import { useNavigate, Link } from 'react-router'
import { toast } from 'sonner'

import { LoginForm } from '@/features/auth/components/LoginForm'
import { AuthLayoutCard } from '@/layouts/AuthLayout'

/**
 * 登录页面组件
 *
 * 提供用户登录入口，包含：
 * - 登录表单（用户名、密码）
 * - 登录成功后跳转到 /dashboard
 * - 注册页面链接
 *
 * @example
 * ```tsx
 * // 在路由配置中使用
 * {
 *   path: '/login',
 *   element: <LoginPage />
 * }
 * ```
 */
export function LoginPage() {
  const navigate = useNavigate()

  /**
   * 登录成功处理
   * Validates: Requirement 5.5 - 登录成功跳转到 /dashboard 页面
   */
  const handleSuccess = () => {
    toast.success('登录成功')
    navigate('/dashboard')
  }

  /**
   * 登录失败处理
   * 显示错误提示信息
   */
  const handleError = (error: string) => {
    toast.error(error)
  }

  return (
    <AuthLayoutCard
      title="登录"
      description="欢迎回来，请登录您的账号"
    >
      {/* 登录表单 */}
      <LoginForm
        onSuccess={handleSuccess}
        onError={handleError}
      />

      {/* 注册页面链接 - Validates: Requirement 5.6 */}
      <div className="mt-6 text-center text-sm text-muted-foreground">
        还没有账号？{' '}
        <Link
          to="/register"
          className="font-medium text-primary hover:underline underline-offset-4 transition-colors"
        >
          立即注册
        </Link>
      </div>
    </AuthLayoutCard>
  )
}

export default LoginPage
