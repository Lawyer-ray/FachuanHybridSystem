/**
 * RegisterPage - 注册页面
 *
 * 集成 RegisterForm、PendingApproval 和 AuthLayoutCard，实现完整的注册功能。
 *
 * @validates Requirements 6.4 - 首位用户注册成功自动跳转到 /dashboard
 * @validates Requirements 6.5 - 后续用户注册成功显示"等待审批"提示页面
 * @validates Requirements 6.6 - 提供跳转到登录页面的链接
 * @validates Requirements 6.7 - 支持明暗主题切换（通过 AuthLayout 实现）
 */

import { useState } from 'react'
import { useNavigate, Link } from 'react-router'
import { toast } from 'sonner'

import { RegisterForm } from '@/features/auth/components/RegisterForm'
import { PendingApproval } from '@/features/auth/components/PendingApproval'
import { AuthLayoutCard } from '@/layouts/AuthLayout'

/**
 * 注册页面组件
 *
 * 提供用户注册入口，包含：
 * - 注册表单（用户名、密码、确认密码、真实姓名、手机号）
 * - 首位用户注册成功后自动跳转到 /dashboard
 * - 后续用户注册成功后显示等待审批页面
 * - 登录页面链接
 *
 * @example
 * ```tsx
 * // 在路由配置中使用
 * {
 *   path: '/register',
 *   element: <RegisterPage />
 * }
 * ```
 */
export function RegisterPage() {
  const navigate = useNavigate()

  /**
   * 控制是否显示等待审批页面
   * 当后续用户注册成功时设置为 true
   */
  const [showPendingApproval, setShowPendingApproval] = useState(false)

  /**
   * 注册成功处理
   *
   * @param requiresApproval - 是否需要审批
   * - true: 后续用户，显示等待审批页面 (Validates: Requirement 6.5)
   * - false: 首位用户，自动跳转到 dashboard (Validates: Requirement 6.4)
   */
  const handleSuccess = (requiresApproval: boolean) => {
    if (requiresApproval) {
      // 后续用户，显示等待审批页面
      // Validates: Requirement 6.5
      setShowPendingApproval(true)
    } else {
      // 首位用户，自动跳转到 dashboard
      // Validates: Requirement 6.4
      toast.success('注册成功，您是首位用户，已自动成为管理员')
      navigate('/dashboard')
    }
  }

  /**
   * 注册失败处理
   * 显示错误提示信息
   */
  const handleError = (error: string) => {
    toast.error(error)
  }

  // 显示等待审批页面
  // Validates: Requirement 6.5
  if (showPendingApproval) {
    return (
      <AuthLayoutCard title="等待审批">
        <PendingApproval />
      </AuthLayoutCard>
    )
  }

  // 显示注册表单
  return (
    <AuthLayoutCard
      title="注册"
      description="创建您的账号"
    >
      {/* 注册表单 */}
      <RegisterForm
        onSuccess={handleSuccess}
        onError={handleError}
      />

      {/* 登录页面链接 - Validates: Requirement 6.6 */}
      <div className="mt-6 text-center text-sm text-muted-foreground">
        已有账号？{' '}
        <Link
          to="/login"
          className="font-medium text-primary hover:underline underline-offset-4 transition-colors"
        >
          立即登录
        </Link>
      </div>
    </AuthLayoutCard>
  )
}

export default RegisterPage
