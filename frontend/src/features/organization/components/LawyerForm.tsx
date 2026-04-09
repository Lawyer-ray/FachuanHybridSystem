/**
 * LawyerForm Component
 *
 * 律师表单组件
 * - 实现表单字段（用户名、密码、真实姓名、手机号、执业证号、身份证号、所属律所、是否管理员）
 * - 支持执业证 PDF 文件上传
 * - 使用 React Hook Form + Zod 验证
 * - 实现保存和取消按钮
 * - 支持创建和编辑模式
 * - 编辑模式下预填充现有数据
 * - 编辑模式密码可选
 * - 响应式布局：移动端单列，桌面端双列
 * - 触摸友好：所有交互元素最小 44px 点击区域
 *
 * Requirements: 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14, 3.15, 3.16
 */

import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useNavigate } from 'react-router'
import { Eye, EyeOff, FileText, Loader2, Save, Upload, X } from 'lucide-react'
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
  FormDescription,
} from '@/components/ui/form'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

import { useLawyer } from '../hooks/use-lawyer'
import { useLawyerMutations } from '../hooks/use-lawyer-mutations'
import { useLawFirms } from '../hooks/use-lawfirms'
import { generatePath } from '@/routes/paths'
import type { FormMode } from '../types'

// ============================================================================
// Types
// ============================================================================

export interface LawyerFormProps {
  /** 律师 ID（编辑模式时传入） */
  lawyerId?: string | number
  /** 表单模式：创建或编辑 */
  mode: FormMode
}

// ============================================================================
// Zod Validation Schema
// ============================================================================

/**
 * 律师表单验证 Schema
 *
 * Requirements:
 * - 3.9: 表单包含字段：用户名（必填）、密码（创建时必填）、真实姓名、手机号、执业证号、身份证号、所属律所、是否管理员
 * - 3.11: 对必填字段进行验证
 * - 3.16: 编辑模式密码可选（留空表示不修改）
 *
 * Note: Password validation is handled conditionally in the component based on mode
 */
const lawyerFormSchema = z.object({
  username: z.string().min(1, '用户名不能为空'),
  password: z.string(),
  real_name: z.string(),
  phone: z.string(),
  license_no: z.string(),
  id_card: z.string(),
  law_firm_id: z.string(),
  is_admin: z.boolean(),
})

type LawyerFormData = z.infer<typeof lawyerFormSchema>

// ============================================================================
// Main Component
// ============================================================================

/**
 * 律师表单组件
 *
 * Requirements:
 * - 3.8: 提供表单编辑律师信息
 * - 3.9: 表单包含字段：用户名（必填）、密码（创建时必填）、真实姓名、手机号、执业证号、身份证号、所属律所、是否管理员
 * - 3.10: 支持执业证 PDF 文件上传
 * - 3.11: 对必填字段进行验证
 * - 3.12: 用户点击「保存」按钮且表单验证通过时，保存数据并显示成功提示
 * - 3.13: 保存成功后导航到详情页
 * - 3.14: 用户点击「取消」按钮时返回上一页
 * - 3.15: 编辑模式下预填充现有数据
 * - 3.16: 编辑模式密码可选
 */
export function LawyerForm({ lawyerId, mode }: LawyerFormProps) {
  const navigate = useNavigate()
  const isEditMode = mode === 'edit'

  // ========== Local State ==========

  // 密码显示/隐藏状态
  const [showPassword, setShowPassword] = useState(false)

  // 执业证 PDF 文件状态 - Requirements: 3.10
  const [licensePdf, setLicensePdf] = useState<File | null>(null)

  // ========== Data Fetching ==========

  // 编辑模式下获取律师数据 - Requirements: 3.15
  const {
    data: lawyer,
    isLoading: isLoadingLawyer,
    error: lawyerError,
  } = useLawyer(lawyerId?.toString() || '')

  // 获取律所列表用于下拉选择
  const { data: lawFirms, isLoading: isLoadingLawFirms } = useLawFirms()

  // 获取 mutations
  const { createLawyer, updateLawyer } = useLawyerMutations()

  // ========== Form Setup ==========

  // 初始化表单，使用 Zod schema 进行验证 - Requirements: 3.11
  const form = useForm<LawyerFormData>({
    resolver: zodResolver(lawyerFormSchema),
    defaultValues: {
      username: '',
      password: '',
      real_name: '',
      phone: '',
      license_no: '',
      id_card: '',
      law_firm_id: '',
      is_admin: false,
    },
  })

  // ========== Effects ==========

  // 编辑模式下预填充现有数据 - Requirements: 3.15
  useEffect(() => {
    if (isEditMode && lawyer) {
      form.reset({
        username: lawyer.username,
        password: '', // 密码不预填充 - Requirements: 3.16
        real_name: lawyer.real_name || '',
        phone: lawyer.phone || '',
        license_no: lawyer.license_no || '',
        id_card: lawyer.id_card || '',
        law_firm_id: lawyer.law_firm?.toString() || '',
        is_admin: lawyer.is_admin,
      })
    }
  }, [isEditMode, lawyer, form])

  // ========== Event Handlers ==========

  /**
   * 文件选择处理
   * Requirements: 3.10
   */
  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (file) {
      // 验证文件类型
      if (file.type !== 'application/pdf') {
        toast.error('请选择 PDF 文件')
        return
      }
      // 验证文件大小（最大 10MB）
      if (file.size > 10 * 1024 * 1024) {
        toast.error('文件大小不能超过 10MB')
        return
      }
      setLicensePdf(file)
    }
  }

  /**
   * 清除已选文件
   */
  const handleClearFile = () => {
    setLicensePdf(null)
  }

  /**
   * 表单提交处理
   * Requirements: 3.12, 3.13
   */
  const onSubmit = (data: LawyerFormData) => {
    // 创建模式下验证密码 - Requirements: 3.11
    if (!isEditMode && (!data.password || data.password.length < 6)) {
      form.setError('password', {
        type: 'manual',
        message: '密码至少6位',
      })
      return
    }

    // 准备提交数据
    const submitData = {
      username: data.username,
      real_name: data.real_name || undefined,
      phone: data.phone || undefined,
      license_no: data.license_no || undefined,
      id_card: data.id_card || undefined,
      law_firm_id: data.law_firm_id ? Number(data.law_firm_id) : undefined,
      is_admin: data.is_admin,
    }

    if (isEditMode && lawyerId) {
      // 更新律师 - Requirements: 3.16 (密码可选)
      const updateData = {
        ...submitData,
        password: data.password || undefined, // 空字符串转为 undefined
      }

      updateLawyer.mutate(
        {
          id: Number(lawyerId),
          data: updateData,
          licensePdf: licensePdf || undefined,
        },
        {
          onSuccess: (updatedLawyer) => {
            // Requirements: 3.12 - 显示成功提示
            toast.success('保存成功')
            // Requirements: 3.13 - 导航到详情页
            navigate(generatePath.lawyerDetail(updatedLawyer.id))
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
      // 创建律师
      const createData = {
        ...submitData,
        password: data.password, // 创建时密码必填
      }

      createLawyer.mutate(
        {
          data: createData,
          licensePdf: licensePdf || undefined,
        },
        {
          onSuccess: (createdLawyer) => {
            // Requirements: 3.12 - 显示成功提示
            toast.success('创建成功')
            // Requirements: 3.13 - 导航到详情页
            navigate(generatePath.lawyerDetail(createdLawyer.id))
          },
          onError: (error) => {
            // 显示错误信息
            const errorMessage =
              error instanceof Error ? error.message : '创建失败，请重试'
            toast.error(errorMessage)
          },
        }
      )
    }
  }

  /**
   * 取消按钮处理
   * Requirements: 3.14
   */
  const handleCancel = () => {
    navigate(-1)
  }

  // ========== Loading & Error States ==========

  // 编辑模式下加载律师数据时显示加载状态
  if (isEditMode && isLoadingLawyer) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="text-muted-foreground size-8 animate-spin" />
      </div>
    )
  }

  // 编辑模式下加载失败时显示错误
  if (isEditMode && lawyerError) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <p className="text-destructive mb-4">加载律师数据失败</p>
        <Button variant="outline" onClick={() => navigate(-1)}>
          返回
        </Button>
      </div>
    )
  }

  const isPending = createLawyer.isPending || updateLawyer.isPending

  // ========== Render ==========

  return (
    <div className="space-y-6">
      {/* 表单卡片 - Requirements: 3.8 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {isEditMode ? '编辑律师信息' : '律师信息'}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
              {/* 表单字段网格布局 - 响应式：移动端单列，桌面端双列 */}
              {/* Requirements: 6.3 (< 768px 单列), 6.4 (>= 1024px 双列) */}
              <div className="grid gap-4 lg:grid-cols-2">
                {/* 用户名字段 - Requirements: 3.9 (必填), 6.5 (触摸区域 44px) */}
                <FormField
                  control={form.control}
                  name="username"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        用户名 <span className="text-destructive">*</span>
                      </FormLabel>
                      <FormControl>
                        <Input
                          placeholder="请输入用户名"
                          disabled={isPending || isEditMode}
                          className="h-11"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                      {isEditMode && (
                        <FormDescription>编辑模式下用户名不可修改</FormDescription>
                      )}
                    </FormItem>
                  )}
                />

                {/* 密码字段 - Requirements: 3.9, 3.16 (编辑模式可选) */}
                <FormField
                  control={form.control}
                  name="password"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        密码{' '}
                        {!isEditMode && <span className="text-destructive">*</span>}
                      </FormLabel>
                      <FormControl>
                        <div className="relative">
                          <Input
                            type={showPassword ? 'text' : 'password'}
                            placeholder={
                              isEditMode ? '留空表示不修改密码' : '请输入密码（至少6位）'
                            }
                            disabled={isPending}
                            className="h-11 pr-10"
                            {...field}
                          />
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="absolute right-0 top-0 h-11 px-3 hover:bg-transparent"
                            onClick={() => setShowPassword(!showPassword)}
                          >
                            {showPassword ? (
                              <EyeOff className="text-muted-foreground size-4" />
                            ) : (
                              <Eye className="text-muted-foreground size-4" />
                            )}
                          </Button>
                        </div>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* 真实姓名字段 - Requirements: 3.9 */}
                <FormField
                  control={form.control}
                  name="real_name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>真实姓名</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="请输入真实姓名"
                          disabled={isPending}
                          className="h-11"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* 手机号字段 - Requirements: 3.9 */}
                <FormField
                  control={form.control}
                  name="phone"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>手机号</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="请输入手机号"
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

                {/* 执业证号字段 - Requirements: 3.9 */}
                <FormField
                  control={form.control}
                  name="license_no"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>执业证号</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="请输入执业证号"
                          disabled={isPending}
                          className="h-11"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* 身份证号字段 - Requirements: 3.9 */}
                <FormField
                  control={form.control}
                  name="id_card"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>身份证号</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="请输入身份证号"
                          disabled={isPending}
                          className="h-11"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* 所属律所字段 - Requirements: 3.9 */}
                <FormField
                  control={form.control}
                  name="law_firm_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>所属律所</FormLabel>
                      <Select
                        onValueChange={field.onChange}
                        value={field.value}
                        disabled={isPending || isLoadingLawFirms}
                      >
                        <FormControl>
                          <SelectTrigger className="h-11 w-full">
                            <SelectValue placeholder="请选择所属律所" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {lawFirms?.map((lawFirm) => (
                            <SelectItem
                              key={lawFirm.id}
                              value={lawFirm.id.toString()}
                            >
                              {lawFirm.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* 是否管理员字段 - Requirements: 3.9 */}
                <FormField
                  control={form.control}
                  name="is_admin"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>是否管理员</FormLabel>
                      <FormControl>
                        <div className="flex h-11 items-center">
                          <label className="relative inline-flex cursor-pointer items-center">
                            <input
                              type="checkbox"
                              className="peer sr-only"
                              checked={field.value}
                              onChange={field.onChange}
                              disabled={isPending}
                            />
                            <div className="peer bg-muted peer-checked:bg-primary peer-focus:ring-ring h-6 w-11 rounded-full after:absolute after:left-[2px] after:top-[2px] after:size-5 after:rounded-full after:border after:border-gray-300 after:bg-white after:transition-all after:content-[''] peer-checked:after:translate-x-full peer-checked:after:border-white peer-focus:ring-2 peer-focus:ring-offset-2 peer-disabled:cursor-not-allowed peer-disabled:opacity-50"></div>
                            <span className="text-muted-foreground ml-3 text-sm">
                              {field.value ? '是' : '否'}
                            </span>
                          </label>
                        </div>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              {/* 执业证 PDF 上传 - Requirements: 3.10 */}
              <div className="space-y-2">
                <FormLabel>执业证 PDF</FormLabel>
                <div className="flex flex-col gap-3">
                  {/* 已选文件显示 */}
                  {licensePdf && (
                    <div className="bg-muted flex items-center gap-2 rounded-md p-3">
                      <FileText className="text-muted-foreground size-5" />
                      <span className="flex-1 truncate text-sm">
                        {licensePdf.name}
                      </span>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={handleClearFile}
                        disabled={isPending}
                      >
                        <X className="size-4" />
                      </Button>
                    </div>
                  )}

                  {/* 已有执业证显示（编辑模式） */}
                  {isEditMode && lawyer?.license_pdf_url && !licensePdf && (
                    <div className="bg-muted flex items-center gap-2 rounded-md p-3">
                      <FileText className="text-muted-foreground size-5" />
                      <a
                        href={lawyer.license_pdf_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary flex-1 truncate text-sm hover:underline"
                      >
                        查看当前执业证
                      </a>
                    </div>
                  )}

                  {/* 文件上传按钮 */}
                  <div className="flex items-center gap-3">
                    <label
                      className={`border-input hover:bg-accent hover:text-accent-foreground inline-flex h-11 cursor-pointer items-center justify-center gap-2 rounded-md border px-4 text-sm font-medium transition-colors ${
                        isPending ? 'pointer-events-none opacity-50' : ''
                      }`}
                    >
                      <Upload className="size-4" />
                      {licensePdf ? '重新选择' : '选择文件'}
                      <input
                        type="file"
                        accept=".pdf,application/pdf"
                        onChange={handleFileChange}
                        disabled={isPending}
                        className="hidden"
                      />
                    </label>
                    <span className="text-muted-foreground text-sm">
                      支持 PDF 格式，最大 10MB
                    </span>
                  </div>
                </div>
              </div>

              {/* 操作按钮 - Requirements: 3.12, 3.14, 6.5 (触摸区域 44px) */}
              <div className="flex flex-col-reverse gap-3 md:flex-row md:justify-end">
                {/* 取消按钮 - Requirements: 3.14, 6.5 */}
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

                {/* 保存按钮 - Requirements: 3.12, 6.5 */}
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

export default LawyerForm
