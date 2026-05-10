import { useState } from 'react'
import { useNavigate, Link } from 'react-router'
import { toast } from 'sonner'
import { UserPlus } from 'lucide-react'

import { RegisterForm } from '@/features/auth/components/RegisterForm'
import { PendingApproval } from '@/features/auth/components/PendingApproval'
import { AuthLayoutCard } from '@/layouts/AuthLayout'

export function RegisterPage() {
  const navigate = useNavigate()
  const [showPendingApproval, setShowPendingApproval] = useState(false)

  const handleSuccess = (requiresApproval: boolean) => {
    if (requiresApproval) {
      setShowPendingApproval(true)
    } else {
      toast.success('注册成功，您是首位用户，已自动成为管理员')
      navigate('/dashboard')
    }
  }

  const handleError = (error: string) => {
    toast.error(error)
  }

  if (showPendingApproval) {
    return (
      <AuthLayoutCard title="等待审批">
        <PendingApproval />
      </AuthLayoutCard>
    )
  }

  return (
    <AuthLayoutCard
      title="注册"
      description="创建您的账号"
      icon={<UserPlus className="h-10 w-10 text-violet-400" />}
    >
      <RegisterForm
        onSuccess={handleSuccess}
        onError={handleError}
      />

      <div className="mt-6 text-center text-sm text-muted-foreground">
        已有账号？{' '}
        <Link
          to="/login"
          className="font-medium text-primary dark:text-violet-300 dark:hover:text-violet-200 hover:underline underline-offset-4 transition-colors"
        >
          立即登录
        </Link>
      </div>
    </AuthLayoutCard>
  )
}

export default RegisterPage
