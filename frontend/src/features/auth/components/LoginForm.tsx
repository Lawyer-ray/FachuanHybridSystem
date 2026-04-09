/**
 * LoginForm 组件
 * 登录表单组件，使用 React Hook Form + Zod 验证
 *
 * Requirements:
 * - 5.1: 显示用户名和密码输入框
 * - 5.2: 使用 Zod 进行表单验证
 * - 5.3: 表单验证失败时显示对应的错误提示
 * - 5.4: 登录请求进行中时显示加载状态
 */

import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2 } from 'lucide-react'

import { loginSchema, type LoginFormData } from '../schemas'
import { useLoginMutation } from '../hooks/use-auth-mutations'
import {
  Form,
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'

interface LoginFormProps {
  /** 登录成功回调 */
  onSuccess?: () => void
  /** 登录失败回调 */
  onError?: (error: string) => void
}

/**
 * 登录表单组件
 *
 * 提供用户名和密码输入，使用 Zod 进行表单验证，
 * 支持加载状态显示和错误提示。
 *
 * @example
 * ```tsx
 * function LoginPage() {
 *   const navigate = useNavigate()
 *
 *   return (
 *     <LoginForm
 *       onSuccess={() => navigate('/dashboard')}
 *       onError={(error) => toast.error(error)}
 *     />
 *   )
 * }
 * ```
 */
export function LoginForm({ onSuccess, onError }: LoginFormProps) {
  // 初始化表单，使用 Zod schema 进行验证
  // Validates: Requirement 5.2
  const form = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
    defaultValues: {
      username: '',
      password: '',
    },
  })

  // 登录 mutation hook
  const loginMutation = useLoginMutation()

  // 表单提交处理
  const onSubmit = (data: LoginFormData) => {
    loginMutation.mutate(data, {
      onSuccess: () => {
        onSuccess?.()
      },
      onError: (error) => {
        // 处理登录错误
        const errorMessage = error instanceof Error
          ? error.message
          : '登录失败，请重试'
        onError?.(errorMessage)
      },
    })
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        {/* 用户名输入框 - Validates: Requirement 5.1 */}
        <FormField
          control={form.control}
          name="username"
          render={({ field }) => (
            <FormItem>
              <FormLabel>用户名</FormLabel>
              <FormControl>
                <Input
                  placeholder="请输入用户名"
                  autoComplete="username"
                  disabled={loginMutation.isPending}
                  {...field}
                />
              </FormControl>
              {/* 错误提示 - Validates: Requirement 5.3 */}
              <FormMessage />
            </FormItem>
          )}
        />

        {/* 密码输入框 - Validates: Requirement 5.1 */}
        <FormField
          control={form.control}
          name="password"
          render={({ field }) => (
            <FormItem>
              <FormLabel>密码</FormLabel>
              <FormControl>
                <Input
                  type="password"
                  placeholder="请输入密码"
                  autoComplete="current-password"
                  disabled={loginMutation.isPending}
                  {...field}
                />
              </FormControl>
              {/* 错误提示 - Validates: Requirement 5.3 */}
              <FormMessage />
            </FormItem>
          )}
        />

        {/* 提交按钮 - Validates: Requirement 5.4 */}
        <Button
          type="submit"
          className="w-full"
          disabled={loginMutation.isPending}
        >
          {loginMutation.isPending ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              登录中...
            </>
          ) : (
            '登录'
          )}
        </Button>
      </form>
    </Form>
  )
}

export default LoginForm
