import { useState, useEffect } from 'react'
import { useSearchParams, Link } from 'react-router'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Loader2, CheckCircle2, XCircle, ArrowLeft } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { AuthLayoutCard } from '@/layouts/AuthLayout'
import { authApi } from '@/features/auth/api'

const resetPasswordSchema = z.object({
  new_password: z.string().min(8, '密码至少8个字符'),
  confirm_password: z.string(),
}).refine((data) => data.new_password === data.confirm_password, {
  message: '两次输入的密码不一致',
  path: ['confirm_password'],
})

type ResetPasswordFormData = z.infer<typeof resetPasswordSchema>

type TokenStatus = 'loading' | 'valid' | 'invalid'

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams()
  const uid = searchParams.get('uid') || ''
  const token = searchParams.get('token') || ''

  const [tokenStatus, setTokenStatus] = useState<TokenStatus>('loading')
  const [username, setUsername] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [success, setSuccess] = useState(false)

  const form = useForm<ResetPasswordFormData>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { new_password: '', confirm_password: '' },
  })

  // Verify token on mount
  useEffect(() => {
    if (!uid || !token) {
      setTokenStatus('invalid')
      return
    }

    authApi.verifyPasswordResetToken(uid, token)
      .then((res) => {
        if (res.success && res.data?.is_valid) {
          setTokenStatus('valid')
          setUsername(res.data.username || '')
        } else {
          setTokenStatus('invalid')
        }
      })
      .catch(() => setTokenStatus('invalid'))
  }, [uid, token])

  const onSubmit = async (data: ResetPasswordFormData) => {
    setSubmitting(true)
    try {
      const res = await authApi.confirmPasswordReset({
        uid,
        token,
        new_password: data.new_password,
        confirm_password: data.confirm_password,
      })
      if (res.success) {
        setSuccess(true)
        toast.success('密码重置成功')
      } else {
        toast.error(res.message || '重置失败')
      }
    } catch {
      toast.error('网络错误，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  // Loading state
  if (tokenStatus === 'loading') {
    return (
      <AuthLayoutCard title="验证中">
        <div className="flex flex-col items-center py-8">
          <Loader2 className="size-8 animate-spin text-muted-foreground mb-4" />
          <p className="text-sm text-muted-foreground">正在验证重置链接...</p>
        </div>
      </AuthLayoutCard>
    )
  }

  // Invalid token
  if (tokenStatus === 'invalid') {
    return (
      <AuthLayoutCard title="链接无效">
        <div className="flex flex-col items-center text-center py-4">
          <XCircle className="size-12 text-destructive mb-4" />
          <p className="text-sm text-muted-foreground mb-2">
            密码重置链接无效或已过期。
          </p>
          <p className="text-xs text-muted-foreground mb-6">
            重置链接有效期为 30 分钟，请重新申请。
          </p>
          <Link to="/forgot-password">
            <Button variant="outline" size="sm">
              重新申请重置
            </Button>
          </Link>
        </div>
      </AuthLayoutCard>
    )
  }

  // Success
  if (success) {
    return (
      <AuthLayoutCard title="密码已重置">
        <div className="flex flex-col items-center text-center py-4">
          <CheckCircle2 className="size-12 text-green-500 mb-4" />
          <p className="text-sm text-muted-foreground mb-6">
            您的密码已成功重置，请使用新密码登录。
          </p>
          <Link to="/login">
            <Button size="sm">
              去登录
            </Button>
          </Link>
        </div>
      </AuthLayoutCard>
    )
  }

  // Reset form
  return (
    <AuthLayoutCard
      title="重置密码"
      description={username ? `为账号「${username}」设置新密码` : '请设置新密码'}
    >
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          <FormField
            control={form.control}
            name="new_password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>新密码</FormLabel>
                <FormControl>
                  <Input
                    type="password"
                    placeholder="至少8个字符"
                    disabled={submitting}
                    className="h-11"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="confirm_password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>确认密码</FormLabel>
                <FormControl>
                  <Input
                    type="password"
                    placeholder="再次输入新密码"
                    disabled={submitting}
                    className="h-11"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <Button type="submit" className="w-full h-11" disabled={submitting}>
            {submitting ? (
              <><Loader2 className="mr-2 size-4 animate-spin" />重置中...</>
            ) : (
              '重置密码'
            )}
          </Button>
        </form>
      </Form>

      <div className="mt-6 text-center text-sm text-muted-foreground">
        <Link
          to="/login"
          className="font-medium text-primary hover:underline underline-offset-4 transition-colors"
        >
          <ArrowLeft className="inline size-3.5 mr-1" />返回登录
        </Link>
      </div>
    </AuthLayoutCard>
  )
}

export default ResetPasswordPage
