import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2 } from 'lucide-react'
import { motion } from 'framer-motion'

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
  onSuccess?: (requiresApproval: boolean) => void
  onError?: (error: string) => void
}

export function RegisterForm({ onSuccess, onError }: RegisterFormProps) {
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

  const registerMutation = useRegisterMutation()

  const onSubmit = (data: RegisterFormData) => {
    registerMutation.mutate(
      {
        username: data.username,
        password: data.password,
        real_name: data.real_name || undefined,
        phone: data.phone || undefined,
      },
      {
        onSuccess: (response) => {
          onSuccess?.(response.requires_approval)
        },
        onError: (error) => {
          const errorMessage =
            error instanceof Error ? error.message : '注册失败，请重试'
          onError?.(errorMessage)
        },
      }
    )
  }

  const cosmicInput = 'cosmic-input dark:bg-[rgba(15,10,40,0.4)] dark:border-[rgba(123,97,255,0.2)]'
  const cosmicLabel = 'dark:text-violet-200'

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.15, duration: 0.4 }}
        >
          <FormField
            control={form.control}
            name="username"
            render={({ field }) => (
              <FormItem>
                <FormLabel className={cosmicLabel}>用户名</FormLabel>
                <FormControl>
                  <Input
                    placeholder="请输入用户名（3-20个字符）"
                    autoComplete="username"
                    disabled={registerMutation.isPending}
                    className={cosmicInput}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </motion.div>

        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.23, duration: 0.4 }}
        >
          <FormField
            control={form.control}
            name="password"
            render={({ field }) => (
              <FormItem>
                <FormLabel className={cosmicLabel}>密码</FormLabel>
                <FormControl>
                  <Input
                    type="password"
                    placeholder="请输入密码（6-32个字符）"
                    autoComplete="new-password"
                    disabled={registerMutation.isPending}
                    className={cosmicInput}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </motion.div>

        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.31, duration: 0.4 }}
        >
          <FormField
            control={form.control}
            name="confirmPassword"
            render={({ field }) => (
              <FormItem>
                <FormLabel className={cosmicLabel}>确认密码</FormLabel>
                <FormControl>
                  <Input
                    type="password"
                    placeholder="请再次输入密码"
                    autoComplete="new-password"
                    disabled={registerMutation.isPending}
                    className={cosmicInput}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </motion.div>

        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.39, duration: 0.4 }}
        >
          <FormField
            control={form.control}
            name="real_name"
            render={({ field }) => (
              <FormItem>
                <FormLabel className={cosmicLabel}>
                  真实姓名
                  <span className="ml-1 text-xs text-muted-foreground">（可选）</span>
                </FormLabel>
                <FormControl>
                  <Input
                    placeholder="请输入真实姓名"
                    autoComplete="name"
                    disabled={registerMutation.isPending}
                    className={cosmicInput}
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </motion.div>

        <motion.div
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.47, duration: 0.4 }}
        >
          <FormField
            control={form.control}
            name="phone"
            render={({ field }) => (
              <FormItem>
                <FormLabel className={cosmicLabel}>
                  手机号
                  <span className="ml-1 text-xs text-muted-foreground">（可选）</span>
                </FormLabel>
                <FormControl>
                  <Input
                    type="tel"
                    placeholder="请输入手机号"
                    autoComplete="tel"
                    disabled={registerMutation.isPending}
                    className={cosmicInput}
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
          transition={{ delay: 0.55, duration: 0.4 }}
        >
          <Button
            type="submit"
            className="w-full cosmic-btn cosmic-btn-shimmer"
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
        </motion.div>
      </form>
    </Form>
  )
}

export default RegisterForm
