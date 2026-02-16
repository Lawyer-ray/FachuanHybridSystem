/**
 * CredentialFormDialog Component
 *
 * 凭证表单对话框组件
 * - 实现表单字段（所属律师、网站名称、URL、账号、密码）
 * - 密码字段支持显示/隐藏切换
 * - 使用 React Hook Form + Zod 验证
 * - 支持创建和编辑模式
 * - 编辑模式下预填充现有数据（密码字段除外）
 * - 编辑模式密码可选（留空表示不修改）
 * - 保存成功后关闭对话框
 * - 显示成功/失败提示
 *
 * Requirements:
 * - 5.4: 提供表单编辑凭证信息
 * - 5.8: 表单包含字段：所属律师（必填）、网站名称（必填）、URL、账号（必填）、密码（创建时必填）
 * - 5.9: 对必填字段进行验证
 * - 5.10: 用户点击「保存」按钮且表单验证通过时，保存数据并显示成功提示
 * - 5.11: 保存成功后关闭对话框
 * - 5.12: 用户点击「取消」按钮时关闭对话框
 * - 5.13: 编辑模式下预填充现有数据
 * - 5.14: 编辑模式密码可选
 * - 5.15: 保存失败时显示错误信息
 * - 5.18: 密码字段支持显示/隐藏切换
 */

import { useEffect, useCallback, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Loader2, Save, X, Eye, EyeOff } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Form,
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormMessage,
  FormDescription,
} from '@/components/ui/form'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

import { useCredentialMutations } from '../hooks/use-credential-mutations'
import { useLawyers } from '../hooks/use-lawyers'
import type { AccountCredential } from '../types'

// ============================================================================
// Types
// ============================================================================

/**
 * CredentialFormDialog 组件属性
 */
export interface CredentialFormDialogProps {
  /** 对话框打开状态 */
  open: boolean
  /** 对话框状态变更回调 */
  onOpenChange: (open: boolean) => void
  /** 编辑模式下的凭证数据（如果提供则为编辑模式，否则为创建模式） */
  credential?: AccountCredential
}

// ============================================================================
// Zod Validation Schema
// ============================================================================

/**
 * 凭证表单验证 Schema
 * 使用单一 schema，密码验证在 onSubmit 中手动处理
 *
 * Requirements:
 * - 5.8: 表单包含字段：所属律师（必填）、网站名称（必填）、URL、账号（必填）、密码（创建时必填）
 * - 5.9: 对必填字段进行验证
 * - 5.14: 编辑模式密码可选
 */
const credentialFormSchema = z.object({
  lawyer_id: z.number({ message: '请选择所属律师' }).min(1, '请选择所属律师'),
  site_name: z.string().min(1, '网站名称不能为空'),
  url: z.string().optional(),
  account: z.string().min(1, '账号不能为空'),
  password: z.string(),
})

type CredentialFormData = z.infer<typeof credentialFormSchema>

// ============================================================================
// Main Component
// ============================================================================

/**
 * 凭证表单对话框组件
 *
 * 提供以下功能：
 * - 封装 Dialog + Form
 * - 处理创建和编辑两种模式
 * - 密码字段支持显示/隐藏切换
 * - 成功时关闭对话框并显示成功提示
 * - 失败时显示错误提示并保留表单数据
 *
 * Requirements: 5.4, 5.8, 5.9, 5.10, 5.11, 5.12, 5.13, 5.14, 5.15, 5.18
 */
export function CredentialFormDialog({
  open,
  onOpenChange,
  credential,
}: CredentialFormDialogProps) {
  const isEditMode = !!credential

  // ========== Local State ==========

  // 密码显示/隐藏状态 - Requirements: 5.18
  const [showPassword, setShowPassword] = useState(false)

  // ========== Data Fetching ==========

  // 获取律师列表用于下拉选择
  const { data: lawyers = [], isLoading: isLoadingLawyers } = useLawyers()

  // 获取 mutations
  const { createCredential, updateCredential } = useCredentialMutations()

  const isPending = createCredential.isPending || updateCredential.isPending

  // ========== Form Setup ==========

  // 初始化表单，使用 Zod schema 进行验证 - Requirements: 5.9
  // 密码验证在 onSubmit 中手动处理（创建时必填，编辑时可选）
  const form = useForm<CredentialFormData>({
    resolver: zodResolver(credentialFormSchema),
    defaultValues: {
      lawyer_id: undefined,
      site_name: '',
      url: '',
      account: '',
      password: '',
    },
  })

  // ========== Effects ==========

  // 编辑模式下预填充现有数据（密码字段除外） - Requirements: 5.13
  useEffect(() => {
    if (open) {
      // 重置密码显示状态
      setShowPassword(false)

      if (isEditMode && credential) {
        form.reset({
          lawyer_id: credential.lawyer,
          site_name: credential.site_name,
          url: credential.url || '',
          account: credential.account,
          password: '', // 密码字段不预填充
        })
      } else {
        // 创建模式下重置表单
        form.reset({
          lawyer_id: undefined,
          site_name: '',
          url: '',
          account: '',
          password: '',
        })
      }
    }
  }, [open, isEditMode, credential, form])

  // ========== Event Handlers ==========

  /**
   * 切换密码显示/隐藏
   * Requirements: 5.18
   */
  const togglePasswordVisibility = useCallback(() => {
    setShowPassword((prev) => !prev)
  }, [])

  /**
   * 表单提交处理
   * Requirements: 5.10, 5.11, 5.15
   */
  const onSubmit = useCallback(
    (data: CredentialFormData) => {
      // 创建模式下密码必填验证 - Requirements: 5.8, 5.9
      if (!isEditMode && (!data.password || data.password.trim() === '')) {
        form.setError('password', { message: '密码不能为空' })
        return
      }

      if (isEditMode && credential) {
        // 更新凭证
        const updateData: {
          site_name?: string
          url?: string
          account?: string
          password?: string
        } = {
          site_name: data.site_name,
          url: data.url || undefined,
          account: data.account,
        }

        // 只有当密码不为空时才更新密码 - Requirements: 5.14
        if (data.password && data.password.trim() !== '') {
          updateData.password = data.password
        }

        updateCredential.mutate(
          { id: credential.id, data: updateData },
          {
            onSuccess: () => {
              // Requirements: 5.10 - 显示成功提示
              toast.success('凭证更新成功')
              // Requirements: 5.11 - 关闭对话框
              onOpenChange(false)
            },
            onError: (error) => {
              // Requirements: 5.15 - 显示错误信息
              const errorMessage =
                error instanceof Error ? error.message : '更新失败，请重试'
              toast.error(errorMessage)
              // 保留表单数据，不关闭对话框
            },
          }
        )
      } else {
        // 创建凭证
        const createData = {
          lawyer_id: data.lawyer_id,
          site_name: data.site_name,
          url: data.url || undefined,
          account: data.account,
          password: data.password,
        }

        createCredential.mutate(createData, {
          onSuccess: () => {
            // Requirements: 5.10 - 显示成功提示
            toast.success('凭证创建成功')
            // Requirements: 5.11 - 关闭对话框
            onOpenChange(false)
          },
          onError: (error) => {
            // Requirements: 5.15 - 显示错误信息
            const errorMessage =
              error instanceof Error ? error.message : '创建失败，请重试'
            toast.error(errorMessage)
            // 保留表单数据，不关闭对话框
          },
        })
      }
    },
    [isEditMode, credential, createCredential, updateCredential, onOpenChange]
  )

  /**
   * 取消按钮处理
   * Requirements: 5.12
   */
  const handleCancel = useCallback(() => {
    onOpenChange(false)
  }, [onOpenChange])

  // ========== Render ==========

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>
            {isEditMode ? '编辑凭证' : '新建凭证'}
          </DialogTitle>
          <DialogDescription>
            {isEditMode
              ? '修改凭证信息，完成后点击保存'
              : '填写凭证信息，创建新的账号凭证'}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            {/* 所属律师字段 - Requirements: 5.8 (必填) */}
            <FormField
              control={form.control}
              name="lawyer_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    所属律师 <span className="text-destructive">*</span>
                  </FormLabel>
                  <Select
                    onValueChange={(value) => field.onChange(Number(value))}
                    value={field.value?.toString()}
                    disabled={isPending || isLoadingLawyers}
                  >
                    <FormControl>
                      <SelectTrigger className="h-11 w-full">
                        <SelectValue placeholder={isLoadingLawyers ? '加载中...' : '请选择所属律师'} />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {lawyers.map((lawyer) => (
                        <SelectItem key={lawyer.id} value={lawyer.id.toString()}>
                          {lawyer.real_name || lawyer.username}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* 网站名称字段 - Requirements: 5.8 (必填) */}
            <FormField
              control={form.control}
              name="site_name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    网站名称 <span className="text-destructive">*</span>
                  </FormLabel>
                  <FormControl>
                    <Input
                      placeholder="请输入网站名称"
                      disabled={isPending}
                      className="h-11"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* URL 字段 - Requirements: 5.8 (可选) */}
            <FormField
              control={form.control}
              name="url"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>URL</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="请输入网站URL（可选）"
                      disabled={isPending}
                      className="h-11"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* 账号字段 - Requirements: 5.8 (必填) */}
            <FormField
              control={form.control}
              name="account"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    账号 <span className="text-destructive">*</span>
                  </FormLabel>
                  <FormControl>
                    <Input
                      placeholder="请输入账号"
                      disabled={isPending}
                      className="h-11"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* 密码字段 - Requirements: 5.8 (创建时必填), 5.14 (编辑时可选), 5.18 (显示/隐藏切换) */}
            <FormField
              control={form.control}
              name="password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    密码 {!isEditMode && <span className="text-destructive">*</span>}
                  </FormLabel>
                  <FormControl>
                    <div className="relative">
                      <Input
                        type={showPassword ? 'text' : 'password'}
                        placeholder={isEditMode ? '留空表示不修改' : '请输入密码'}
                        disabled={isPending}
                        className="h-11 pr-10"
                        {...field}
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="absolute right-0 top-0 h-11 px-3 hover:bg-transparent"
                        onClick={togglePasswordVisibility}
                        disabled={isPending}
                        tabIndex={-1}
                      >
                        {showPassword ? (
                          <EyeOff className="size-4 text-muted-foreground" />
                        ) : (
                          <Eye className="size-4 text-muted-foreground" />
                        )}
                        <span className="sr-only">
                          {showPassword ? '隐藏密码' : '显示密码'}
                        </span>
                      </Button>
                    </div>
                  </FormControl>
                  {isEditMode && (
                    <FormDescription>
                      留空表示不修改密码
                    </FormDescription>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* 操作按钮 - Requirements: 5.10, 5.12 */}
            <DialogFooter className="pt-4">
              {/* 取消按钮 - Requirements: 5.12 */}
              <Button
                type="button"
                variant="outline"
                onClick={handleCancel}
                disabled={isPending}
                className="h-11"
              >
                <X className="mr-2 size-4" />
                取消
              </Button>

              {/* 保存按钮 - Requirements: 5.10 */}
              <Button type="submit" disabled={isPending} className="h-11">
                {isPending ? (
                  <>
                    <Loader2 className="mr-2 size-4 animate-spin" />
                    保存中...
                  </>
                ) : (
                  <>
                    <Save className="mr-2 size-4" />
                    保存
                  </>
                )}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

// ============================================================================
// Default Export
// ============================================================================

export default CredentialFormDialog
