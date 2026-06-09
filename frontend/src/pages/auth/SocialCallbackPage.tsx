/**
 * SocialCallbackPage — 社交登录回调中间页
 *
 * 接收后端重定向的 ?code=xxx&redirect=xxx，
 * 用临时授权码换取 JWT token，然后跳转到目标页面。
 */

import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { socialAuthApi } from '@/features/social-auth/api'
import { useAuthStore } from '@/stores/auth'
import { setTokens } from '@/lib/token'
import { api } from '@/lib/api'

import type { User } from '@/features/auth/types'

export function SocialCallbackPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { login } = useAuthStore()

  useEffect(() => {
    const code = searchParams.get('code')
    const error = searchParams.get('error')
    const redirect = searchParams.get('redirect') || '/dashboard'

    if (error) {
      toast.error('社交登录失败，请重试')
      navigate('/login', { replace: true })
      return
    }

    if (!code) {
      navigate('/login', { replace: true })
      return
    }

    socialAuthApi
      .tokenExchange(code)
      .then(async (res) => {
        if (!res.success) {
          toast.error(res.message || '登录失败')
          navigate('/login', { replace: true })
          return
        }

        setTokens({ access: res.access, refresh: res.refresh })

        const user = await api.get('organization/me').json<User>()

        login(user)

        toast.success('登录成功')
        navigate(redirect, { replace: true })
      })
      .catch(() => {
        toast.error('登录失败，请重试')
        navigate('/login', { replace: true })
      })
  }, [searchParams, navigate, login])

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="flex flex-col items-center space-y-4">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        <p className="text-sm text-muted-foreground">正在完成登录...</p>
      </div>
    </div>
  )
}

export default SocialCallbackPage
