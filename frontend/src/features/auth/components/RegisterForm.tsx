/**
 * RegisterForm 组件
 * 注册表单组件，使用 React Hook Form + Zod 验证
 *
 * Requirements:
 * - 6.1: 显示用户名、密码、确认密码、真实姓名、手机号（可选）输入框
 * - 6.2: 使用 Zod 验证密码一致性和格式要求
 * - 6.3: 表单验证失败时显示对应的错误提示
 */

import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2 } from 'lucide-react'

import { registerSchema, type RegisterFormData } from '../schemas'
import { useRegisterMutation } from '../hooks/use-auth-mutations'
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

interface RegisterFormProps {
  /** 注册成功回调，参数表示是否需要审批 */
  onSuccess?: (requiresApproval: boolean) => void
  /** 注册失败回调 */
  onError?: (error: string) => void
}

/**
 * 注册表单组件
 *
 * 提供用户名、密码、确认密码、真实姓名、手机号输入，
 * 使用 Zod 进行表单验证（包括密码一致性验证），
 * 支持加载状态显示和错误提示。
 *
 * @example
 * ```tsx
 * function RegisterPage() {
 *   const navigate = useNavigate()
 *   const [showPending, setShowPending] = useState(false)
 *
 *   return (
 *     <RegisterForm
 *       onSuccess={(requiresApproval) => {
 *         if (requiresApproval) {
 *           setShowPending(true)
 *         } else {
 *           navigate('/dashboard')
 *         }
 *       }}
 *       onError={(error) => toast.error(error)}
 *     />
 *   )
 * }
 * ```
 */
export function RegisterForm({ onSuccess, onError }: RegisterFormProps) {
  // 初始化表单，使用 Zod schema 进行验证
  // Validates: Requirement 6.2
  const form = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      username: '',
      password: '',
      confirmPassword: '',
      real_name: '',
      phone: '',
    },
  })

  // 注册 mutation hook
  const registerMutation = useRegisterMutation()

  // 表单提交处理
  const onSubmit = (data: RegisterFormData) => {
    registerMutation.mutate(
      {
        username: data.username,
        password: data.password,
        real_name: data.real_name,
        phone: data.phone || undefined,
      },
      {
        onSuccess: (response) => {
          onSuccess?.(response.requires_approval)
        },
        onError: (error) => {
          // 处理注册错误
          const errorMessage =
            error instanceof Error ? error.message : '注册失败，请重试'
          onError?.(errorMessage)
        },
      }
    )
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        {/* 用户名输入框 - Validates: Requirement 6.1 */}
        <FormField
          control={form.control}
          name="username"
          render={({ field }) => (
            <FormItem>
              <FormLabel>用户名</FormLabel>
              <FormControl>
                <Input
                  placeholder="请输入用户名（3-20个字符）"
                  autoComplete="username"
                  disabled={registerMutation.isPending}
                  {...field}
                />
              </FormControl>
              {/* 错误提示 - Validates: Requirement 6.3 */}
              <FormMessage />
            </FormItem>
          )}
        />

        {/* 密码输入框 - Validates: Requirement 6.1 */}
        <FormField
          control={form.control}
          name="password"
          render={({ field }) => (
            <FormItem>
              <FormLabel>密码</FormLabel>
              <FormControl>
                <Input
                  type="password"
                  placeholder="请输入密码（6-32个字符）"
                  autoComplete="new-password"
                  disabled={registerMutation.isPending}
                  {...field}
                />
              </FormControl>
              {/* 错误提示 - Validates: Requirement 6.3 */}
              <FormMessage />
            </FormItem>
          )}
        />

        {/* 确认密码输入框 - Validates: Requirement 6.1, 6.2 */}
        <FormField
          control={form.control}
          name="confirmPassword"
          render={({ field }) => (
            <FormItem>
              <FormLabel>确认密码</FormLabel>
              <FormControl>
                <Input
                  type="password"
                  placeholder="请再次输入密码"
                  autoComplete="new-password"
                  disabled={registerMutation.isPending}
                  {...field}
                />
              </FormControl>
              {/* 密码一致性错误提示 - Validates: Requirement 6.2, 6.3 */}
              <FormMessage />
            </FormItem>
          )}
        />

        {/* 真实姓名输入框 - Validates: Requirement 6.1 */}
        <FormField
          control={form.control}
          name="real_name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>真实姓名</FormLabel>
              <FormControl>
                <Input
                  placeholder="请输入真实姓名"
                  autoComplete="name"
                  disabled={registerMutation.isPending}
                  {...field}
                />
              </FormControl>
              {/* 错误提示 - Validates: Requirement 6.3 */}
              <FormMessage />
            </FormItem>
          )}
        />

        {/* 手机号输入框（可选）- Validates: Requirement 6.1 */}
        <FormField
          control={form.control}
          name="phone"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                手机号
                <span className="ml-1 text-xs text-muted-foreground">
                  （可选）
                </span>
              </FormLabel>
              <FormControl>
                <Input
                  type="tel"
                  placeholder="请输入手机号"
                  autoComplete="tel"
                  disabled={registerMutation.isPending}
                  {...field}
                />
              </FormControl>
              {/* 错误提示 - Validates: Requirement 6.3 */}
              <FormMessage />
            </FormItem>
          )}
        />

        {/* 提交按钮 */}
        <Button
          type="submit"
          className="w-full"
          disabled={registerMutation.isPending}
        >
          {registerMutation.isPending ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              注册中...
            </>
          ) : (
            '注册'
          )}
        </Button>
      </form>
    </Form>
  )
}

export default RegisterForm
