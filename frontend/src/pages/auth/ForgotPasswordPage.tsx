import { useState } from 'react'
import { Link } from 'react-router'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Loader2, Mail, ArrowLeft, CheckCircle2 } from 'lucide-react'
import { toast } from 'sonner'
import { motion } from 'framer-motion'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { AuthLayoutCard } from '@/layouts/AuthLayout'
import { authApi } from '@/features/auth/api'

const forgotPasswordSchema = z.object({
  email: z.string().email('请输入有效的邮箱地址'),
})

type ForgotPasswordFormData = z.infer<typeof forgotPasswordSchema>

export function ForgotPasswordPage() {
  const [submitted, setSubmitted] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const form = useForm<ForgotPasswordFormData>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: '' },
  })

  const onSubmit = async (data: ForgotPasswordFormData) => {
    setSubmitting(true)
    try {
      const res = await authApi.requestPasswordReset(data.email)
      if (res.success) {
        setSubmitted(true)
      } else {
        toast.error(res.message || '请求失败')
      }
    } catch {
      toast.error('网络错误，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  if (submitted) {
    return (
      <AuthLayoutCard title="邮件已发送">
        <div className="flex flex-col items-center text-center py-4">
          <CheckCircle2 className="size-12 text-green-500 mb-4" />
          <p className="text-sm text-muted-foreground mb-2">
            如果该邮箱已注册，我们已向 <span className="font-medium text-foreground">{form.getValues('email')}</span> 发送了密码重置链接。
          </p>
          <p className="text-xs text-muted-foreground mb-6">
            重置链接将在 30 分钟后失效，请尽快完成操作。
          </p>
          <Link to="/login">
            <Button variant="outline" size="sm">
              <ArrowLeft className="mr-1.5 size-4" />返回登录
            </Button>
          </Link>
        </div>
      </AuthLayoutCard>
    )
  }

  return (
    <AuthLayoutCard
      title="忘记密码"
      description="输入您的注册邮箱，我们将发送密码重置链接"
      icon={<Mail className="h-10 w-10 text-violet-400" />}
    >
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.15, duration: 0.4 }}
          >
            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="dark:text-violet-200">邮箱地址</FormLabel>
                  <FormControl>
                    <Input
                      type="email"
                      placeholder="请输入注册时使用的邮箱"
                      disabled={submitting}
                      className="h-11 cosmic-input dark:bg-[rgba(15,10,40,0.4)] dark:border-[rgba(123,97,255,0.2)]"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.23, duration: 0.4 }}
          >
            <Button type="submit" className="w-full h-11 cosmic-btn cosmic-btn-shimmer" disabled={submitting}>
              {submitting ? (
                <><Loader2 className="mr-2 size-4 animate-spin" />发送中...</>
              ) : (
                <><Mail className="mr-2 size-4" />发送重置链接</>
              )}
            </Button>
          </motion.div>
        </form>
      </Form>

      <div className="mt-6 text-center text-sm text-muted-foreground">
        <Link
          to="/login"
          className="font-medium text-primary dark:text-violet-300 dark:hover:text-violet-200 hover:underline underline-offset-4 transition-colors"
        >
          <ArrowLeft className="inline size-3.5 mr-1" />返回登录
        </Link>
      </div>
    </AuthLayoutCard>
  )
}

export default ForgotPasswordPage
