import { useNavigate, useSearchParams, Link } from 'react-router'
import { toast } from 'sonner'
import { Sparkles } from 'lucide-react'

import { LoginForm } from '@/features/auth/components/LoginForm'
import { AuthLayoutCard } from '@/layouts/AuthLayout'

export function LoginPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const handleSuccess = () => {
    toast.success('登录成功')
    const redirect = searchParams.get('redirect')
    navigate(redirect || '/dashboard', { replace: true })
  }

  const handleError = (error: string) => {
    toast.error(error)
  }

  return (
    <AuthLayoutCard
      title="登录"
      description="欢迎回来，请登录您的账号"
      icon={<Sparkles className="h-10 w-10 text-violet-400" />}
    >
      <LoginForm
        onSuccess={handleSuccess}
        onError={handleError}
      />

      <div className="mt-4 text-center text-sm">
        <Link
          to="/forgot-password"
          className="text-muted-foreground hover:text-primary dark:text-violet-300 dark:hover:text-violet-200 transition-colors"
        >
          忘记密码？
        </Link>
      </div>

      <div className="mt-6 text-center text-sm text-muted-foreground">
        还没有账号？{' '}
        <Link
          to="/register"
          className="font-medium text-primary dark:text-violet-300 dark:hover:text-violet-200 hover:underline underline-offset-4 transition-colors"
        >
          立即注册
        </Link>
      </div>
    </AuthLayoutCard>
  )
}

export default LoginPage
