/**
 * LawFirmForm Component
 *
 * 律所表单组件
 * - 实现表单字段（名称、地址、联系电话、统一社会信用代码、开户行、银行账号）
 * - 使用 React Hook Form + Zod 验证
 * - 实现保存和取消按钮
 * - 支持创建和编辑模式
 * - 编辑模式下预填充现有数据
 * - 响应式布局：移动端单列，桌面端双列
 * - 触摸友好：所有交互元素最小 44px 点击区域
 *
 * Requirements: 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 2.13
 */

import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useNavigate } from 'react-router'
import { Loader2, Save, X } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Form,
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormMessage,
} from '@/components/ui/form'

import { useLawFirm } from '../hooks/use-lawfirm'
import { useLawFirmMutations } from '../hooks/use-lawfirm-mutations'
import { generatePath } from '@/routes/paths'
import type { FormMode } from '../types'

// ============================================================================
// Types
// ============================================================================

export interface LawFirmFormProps {
  /** 律所 ID（编辑模式时传入） */
  lawFirmId?: string | number
  /** 表单模式：创建或编辑 */
  mode: FormMode
}

// ============================================================================
// Zod Validation Schema
// ============================================================================

/**
 * 律所表单验证 Schema
 *
 * Requirements:
 * - 2.8: 表单包含字段：名称（必填）、地址、联系电话、统一社会信用代码、开户行、银行账号
 * - 2.9: 对必填字段进行验证
 */
const lawFirmFormSchema = z.object({
  name: z.string().min(1, '律所名称不能为空'),
  address: z.string().optional(),
  phone: z.string().optional(),
  social_credit_code: z.string().optional(),
  bank_name: z.string().optional(),
  bank_account: z.string().optional(),
})

type LawFirmFormData = z.infer<typeof lawFirmFormSchema>

// ============================================================================
// Main Component
// ============================================================================

/**
 * 律所表单组件
 *
 * Requirements:
 * - 2.7: 提供表单编辑律所信息
 * - 2.8: 表单包含字段：名称（必填）、地址、联系电话、统一社会信用代码、开户行、银行账号
 * - 2.9: 对必填字段进行验证
 * - 2.10: 用户点击「保存」按钮且表单验证通过时，保存数据并显示成功提示
 * - 2.11: 保存成功后导航到详情页
 * - 2.12: 用户点击「取消」按钮时返回上一页
 * - 2.13: 编辑模式下预填充现有数据
 */
export function LawFirmForm({ lawFirmId, mode }: LawFirmFormProps) {
  const navigate = useNavigate()
  const isEditMode = mode === 'edit'

  // ========== Data Fetching ==========

  // 编辑模式下获取律所数据 - Requirements: 2.13
  const {
    data: lawFirm,
    isLoading: isLoadingLawFirm,
    error: lawFirmError,
  } = useLawFirm(lawFirmId?.toString() || '')

  // 获取 mutations
  const { createLawFirm, updateLawFirm } = useLawFirmMutations()

  // ========== Form Setup ==========

  // 初始化表单，使用 Zod schema 进行验证 - Requirements: 2.9
  const form = useForm<LawFirmFormData>({
    resolver: zodResolver(lawFirmFormSchema),
    defaultValues: {
      name: '',
      address: '',
      phone: '',
      social_credit_code: '',
      bank_name: '',
      bank_account: '',
    },
  })

  // ========== Effects ==========

  // 编辑模式下预填充现有数据 - Requirements: 2.13
  useEffect(() => {
    if (isEditMode && lawFirm) {
      form.reset({
        name: lawFirm.name,
        address: lawFirm.address || '',
        phone: lawFirm.phone || '',
        social_credit_code: lawFirm.social_credit_code || '',
        bank_name: lawFirm.bank_name || '',
        bank_account: lawFirm.bank_account || '',
      })
    }
  }, [isEditMode, lawFirm, form])

  // ========== Event Handlers ==========

  /**
   * 表单提交处理
   * Requirements: 2.10, 2.11
   */
  const onSubmit = (data: LawFirmFormData) => {
    // 准备提交数据，处理空字符串为 undefined
    const submitData = {
      name: data.name,
      address: data.address || undefined,
      phone: data.phone || undefined,
      social_credit_code: data.social_credit_code || undefined,
      bank_name: data.bank_name || undefined,
      bank_account: data.bank_account || undefined,
    }

    if (isEditMode && lawFirmId) {
      // 更新律所
      updateLawFirm.mutate(
        { id: Number(lawFirmId), data: submitData },
        {
          onSuccess: (updatedLawFirm) => {
            // Requirements: 2.10 - 显示成功提示
            toast.success('保存成功')
            // Requirements: 2.11 - 导航到详情页
            navigate(generatePath.lawFirmDetail(updatedLawFirm.id))
          },
          onError: (error) => {
            // 显示错误信息
            const errorMessage =
              error instanceof Error ? error.message : '保存失败，请重试'
            toast.error(errorMessage)
          },
        }
      )
    } else {
      // 创建律所
      createLawFirm.mutate(submitData, {
        onSuccess: (createdLawFirm) => {
          // Requirements: 2.10 - 显示成功提示
          toast.success('创建成功')
          // Requirements: 2.11 - 导航到详情页
          navigate(generatePath.lawFirmDetail(createdLawFirm.id))
        },
        onError: (error) => {
          // 显示错误信息
          const errorMessage =
            error instanceof Error ? error.message : '创建失败，请重试'
          toast.error(errorMessage)
        },
      })
    }
  }

  /**
   * 取消按钮处理
   * Requirements: 2.12
   */
  const handleCancel = () => {
    navigate(-1)
  }

  // ========== Loading & Error States ==========

  // 编辑模式下加载律所数据时显示加载状态
  if (isEditMode && isLoadingLawFirm) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="text-muted-foreground size-8 animate-spin" />
      </div>
    )
  }

  // 编辑模式下加载失败时显示错误
  if (isEditMode && lawFirmError) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <p className="text-destructive mb-4">加载律所数据失败</p>
        <Button variant="outline" onClick={() => navigate(-1)}>
          返回
        </Button>
      </div>
    )
  }

  const isPending = createLawFirm.isPending || updateLawFirm.isPending

  // ========== Render ==========

  return (
    <div className="space-y-6">
      {/* 表单卡片 - Requirements: 2.7 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {isEditMode ? '编辑律所信息' : '律所信息'}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
              {/* 表单字段网格布局 - 响应式：移动端单列，桌面端双列 */}
              {/* Requirements: 6.3 (< 768px 单列), 6.4 (>= 1024px 双列) */}
              <div className="grid gap-4 lg:grid-cols-2">
                {/* 名称字段 - Requirements: 2.8 (必填), 6.5 (触摸区域 44px) */}
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        名称 <span className="text-destructive">*</span>
                      </FormLabel>
                      <FormControl>
                        <Input
                          placeholder="请输入律所名称"
                          disabled={isPending}
                          className="h-11"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* 联系电话字段 - Requirements: 2.8, 6.5 (触摸区域 44px) */}
                <FormField
                  control={form.control}
                  name="phone"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>联系电话</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="请输入联系电话"
                          type="tel"
                          disabled={isPending}
                          className="h-11"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* 地址字段 - Requirements: 2.8, 6.5 (触摸区域 44px) */}
                <FormField
                  control={form.control}
                  name="address"
                  render={({ field }) => (
                    <FormItem className="lg:col-span-2">
                      <FormLabel>地址</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="请输入律所地址"
                          disabled={isPending}
                          className="h-11"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* 统一社会信用代码字段 - Requirements: 2.8, 6.5 (触摸区域 44px) */}
                <FormField
                  control={form.control}
                  name="social_credit_code"
                  render={({ field }) => (
                    <FormItem className="lg:col-span-2">
                      <FormLabel>统一社会信用代码</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="请输入统一社会信用代码"
                          disabled={isPending}
                          className="h-11"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* 开户行字段 - Requirements: 2.8, 6.5 (触摸区域 44px) */}
                <FormField
                  control={form.control}
                  name="bank_name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>开户行</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="请输入开户行名称"
                          disabled={isPending}
                          className="h-11"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* 银行账号字段 - Requirements: 2.8, 6.5 (触摸区域 44px) */}
                <FormField
                  control={form.control}
                  name="bank_account"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>银行账号</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="请输入银行账号"
                          disabled={isPending}
                          className="h-11"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              {/* 操作按钮 - Requirements: 2.10, 2.12, 6.5 (触摸区域 44px) */}
              <div className="flex flex-col-reverse gap-3 md:flex-row md:justify-end">
                {/* 取消按钮 - Requirements: 2.12, 6.5 */}
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleCancel}
                  disabled={isPending}
                  className="h-11 min-w-[120px]"
                >
                  <X className="mr-2 size-4" />
                  取消
                </Button>

                {/* 保存按钮 - Requirements: 2.10, 6.5 */}
                <Button type="submit" disabled={isPending} className="h-11 min-w-[120px]">
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
              </div>
            </form>
          </Form>
        </CardContent>
      </Card>
    </div>
  )
}

export default LawFirmForm
