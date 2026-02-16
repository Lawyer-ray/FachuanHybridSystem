/**
 * ClientForm Component
 *
 * 当事人表单组件
 * - 实现表单字段（姓名、类型、身份证号、手机号、地址、法定代表人）
 * - 使用 React Hook Form + Zod 验证
 * - 条件显示法定代表人字段
 * - 集成 OcrUploader 自动填充
 * - 实现保存和取消按钮
 * - 响应式布局：移动端单列，桌面端双列
 * - 触摸友好：所有交互元素最小 44px 点击区域
 *
 * Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 6.6, 6.10, 7.3, 7.4, 7.5
 */

import { useEffect, useCallback } from 'react'
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
  FormDescription,
} from '@/components/ui/form'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

import { useClient } from '../hooks/use-client'
import { useClientMutations } from '../hooks/use-client-mutations'
import { OcrUploader } from './OcrUploader'
import { generatePath } from '@/routes/paths'
import type { OcrResult, ClientType, ClientFormMode } from '../types'
import { CLIENT_TYPE_LABELS } from '../types'

// ============================================================================
// Types
// ============================================================================

export interface ClientFormProps {
  /** 当事人 ID（编辑模式时传入） */
  clientId?: string
  /** 表单模式：创建或编辑 */
  mode: ClientFormMode
}

// ============================================================================
// Zod Validation Schema
// ============================================================================

/**
 * 当事人类型枚举值
 */
const clientTypeValues = ['natural', 'legal', 'non_legal_org'] as const

/**
 * 当事人表单验证 Schema
 *
 * Requirements:
 * - 5.2: 表单包含字段：姓名（必填）、类型（必填）、身份证号、手机号、地址
 * - 5.3: 类型选择为法人或非法人组织时，法定代表人字段必填
 * - 5.4: 对必填字段进行验证
 */
const clientFormSchema = z
  .object({
    name: z.string().min(1, '姓名不能为空'),
    client_type: z.enum(clientTypeValues, {
      message: '请选择当事人类型',
    }),
    id_number: z.string().optional(),
    phone: z.string().optional(),
    address: z.string().optional(),
    legal_representative: z.string().optional(),
    legal_representative_id_number: z.string().optional(),
    is_our_client: z.boolean(),
  })
  .refine(
    (data) => {
      // 法人和非法人组织必须填写法定代表人/负责人 - Requirements: 5.3
      if (data.client_type !== 'natural' && !data.legal_representative) {
        return false
      }
      return true
    },
    {
      message: '此字段为必填项',
      path: ['legal_representative'],
    }
  )

type ClientFormData = z.infer<typeof clientFormSchema>

// ============================================================================
// Main Component
// ============================================================================

/**
 * 当事人表单组件
 *
 * Requirements:
 * - 5.1: 提供表单编辑当事人信息
 * - 5.2: 表单包含字段：姓名（必填）、类型（必填）、身份证号、手机号、地址
 * - 5.3: 类型选择为法人或非法人组织时，显示法定代表人字段（必填）
 * - 5.4: 对必填字段进行验证
 * - 5.5: 用户点击「保存」按钮且表单验证通过时，保存数据并显示成功提示
 * - 5.6: 保存成功后导航到详情页
 * - 5.7: 用户点击「取消」按钮时返回上一页
 * - 5.8: 保存失败时显示错误信息
 * - 5.9: 编辑模式下预填充现有数据
 * - 6.6: OCR 识别成功时自动填充对应表单字段
 * - 6.10: 上传的文件作为当事人身份证件保存
 */
export function ClientForm({ clientId, mode }: ClientFormProps) {
  const navigate = useNavigate()
  const isEditMode = mode === 'edit'

  // ========== Data Fetching ==========

  // 编辑模式下获取当事人数据 - Requirements: 5.9
  const {
    data: client,
    isLoading: isLoadingClient,
    error: clientError,
  } = useClient(clientId || '')

  // 获取 mutations
  const { createClient, updateClient } = useClientMutations()

  // ========== Form Setup ==========

  // 初始化表单，使用 Zod schema 进行验证 - Requirements: 5.4
  const form = useForm<ClientFormData>({
    resolver: zodResolver(clientFormSchema),
    defaultValues: {
      name: '',
      client_type: 'natural',
      id_number: '',
      phone: '',
      address: '',
      legal_representative: '',
      legal_representative_id_number: '',
      is_our_client: true,
    },
  })

  // 监听当事人类型变化，用于条件显示法定代表人字段
  const clientType = form.watch('client_type')
  const showLegalRepresentative = clientType !== 'natural'

  // 根据当事人类型获取动态标签
  const idNumberLabel = clientType === 'natural' ? '身份证号' : '统一社会信用代码'
  const idNumberPlaceholder = clientType === 'natural'
    ? '请输入身份证号'
    : '请输入统一社会信用代码'
  const legalRepLabel = clientType === 'non_legal_org' ? '负责人' : '法定代表人'
  const legalRepPlaceholder = clientType === 'non_legal_org'
    ? '请输入负责人姓名'
    : '请输入法定代表人姓名'
  const legalRepDescription = clientType === 'non_legal_org'
    ? '非法人组织必须填写负责人'
    : '法人必须填写法定代表人'

  // ========== Effects ==========

  // 编辑模式下预填充现有数据 - Requirements: 5.9
  useEffect(() => {
    if (isEditMode && client) {
      form.reset({
        name: client.name,
        client_type: client.client_type,
        id_number: client.id_number || '',
        phone: client.phone || '',
        address: client.address || '',
        legal_representative: client.legal_representative || '',
        legal_representative_id_number: client.legal_representative_id_number || '',
        is_our_client: client.is_our_client,
      })
    }
  }, [isEditMode, client, form])

  // ========== Event Handlers ==========

  /**
   * OCR 识别成功回调
   * Requirements: 6.6
   */
  const handleOcrRecognized = useCallback(
    (data: OcrResult) => {
      // 自动填充识别到的字段
      if (data.name) {
        form.setValue('name', data.name, { shouldValidate: true })
      }
      if (data.id_number) {
        form.setValue('id_number', data.id_number, { shouldValidate: true })
      }
      if (data.address) {
        form.setValue('address', data.address, { shouldValidate: true })
      }
      if (data.legal_representative) {
        form.setValue('legal_representative', data.legal_representative, {
          shouldValidate: true,
        })
      }
      // 根据识别结果设置当事人类型
      if (data.client_type) {
        form.setValue('client_type', data.client_type, { shouldValidate: true })
      }
    },
    [form]
  )

  /**
   * OCR 识别失败回调
   */
  const handleOcrError = useCallback((error: string) => {
    // 错误已在 OcrUploader 中通过 toast 显示
    console.error('OCR Error:', error)
  }, [])

  /**
   * 表单提交处理
   * Requirements: 5.5, 5.6, 5.8
   */
  const onSubmit = (data: ClientFormData) => {
    // 准备提交数据，处理空字符串为 null
    const submitData = {
      name: data.name,
      client_type: data.client_type as ClientType,
      id_number: data.id_number || null,
      phone: data.phone || null,
      address: data.address || null,
      legal_representative:
        data.client_type !== 'natural' ? data.legal_representative || null : null,
      legal_representative_id_number:
        data.client_type !== 'natural' ? data.legal_representative_id_number || null : null,
      is_our_client: data.is_our_client,
    }

    if (isEditMode && clientId) {
      // 更新当事人
      updateClient.mutate(
        { id: clientId, data: submitData },
        {
          onSuccess: (updatedClient) => {
            // Requirements: 5.5 - 显示成功提示
            toast.success('保存成功')
            // Requirements: 5.6 - 导航到详情页
            navigate(generatePath.clientDetail(updatedClient.id))
          },
          onError: (error) => {
            // Requirements: 5.8 - 显示错误信息
            const errorMessage =
              error instanceof Error ? error.message : '保存失败，请重试'
            toast.error(errorMessage)
          },
        }
      )
    } else {
      // 创建当事人
      createClient.mutate(submitData, {
        onSuccess: (createdClient) => {
          // Requirements: 5.5 - 显示成功提示
          toast.success('创建成功')
          // Requirements: 5.6 - 导航到详情页
          navigate(generatePath.clientDetail(createdClient.id))
        },
        onError: (error) => {
          // Requirements: 5.8 - 显示错误信息
          const errorMessage =
            error instanceof Error ? error.message : '创建失败，请重试'
          toast.error(errorMessage)
        },
      })
    }
  }

  /**
   * 取消按钮处理
   * Requirements: 5.7
   */
  const handleCancel = () => {
    navigate(-1)
  }

  // ========== Loading & Error States ==========

  // 编辑模式下加载当事人数据时显示加载状态
  if (isEditMode && isLoadingClient) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="text-muted-foreground size-8 animate-spin" />
      </div>
    )
  }

  // 编辑模式下加载失败时显示错误
  if (isEditMode && clientError) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <p className="text-destructive mb-4">加载当事人数据失败</p>
        <Button variant="outline" onClick={() => navigate(-1)}>
          返回
        </Button>
      </div>
    )
  }

  const isPending = createClient.isPending || updateClient.isPending

  // ========== Render ==========

  return (
    <div className="space-y-6">
      {/* OCR 上传组件 - Requirements: 6.6, 6.10 */}
      <OcrUploader onRecognized={handleOcrRecognized} onError={handleOcrError} />

      {/* 表单卡片 - Requirements: 5.1 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {isEditMode ? '编辑当事人信息' : '当事人信息'}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
              {/* 表单字段网格布局 - 响应式：移动端单列，桌面端双列 */}
              {/* Requirements: 7.3 (< 768px 单列), 7.4 (>= 1024px 双列) */}
              <div className="grid gap-4 lg:grid-cols-2">
                {/* 姓名字段 - Requirements: 5.2 (必填), 7.5 (触摸区域 44px) */}
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        姓名 <span className="text-destructive">*</span>
                      </FormLabel>
                      <FormControl>
                        <Input
                          placeholder="请输入姓名或公司名称"
                          disabled={isPending}
                          className="h-11"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* 当事人类型字段 - Requirements: 5.2 (必填), 7.5 (触摸区域 44px) */}
                <FormField
                  control={form.control}
                  name="client_type"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        类型 <span className="text-destructive">*</span>
                      </FormLabel>
                      <Select
                        onValueChange={field.onChange}
                        value={field.value}
                        disabled={isPending}
                      >
                        <FormControl>
                          <SelectTrigger className="h-11 w-full">
                            <SelectValue placeholder="请选择当事人类型" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {Object.entries(CLIENT_TYPE_LABELS).map(([value, label]) => (
                            <SelectItem key={value} value={value} className="min-h-11">
                              {label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* 身份证号/统一社会信用代码字段 - Requirements: 5.2, 7.5 (触摸区域 44px) */}
                <FormField
                  control={form.control}
                  name="id_number"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{idNumberLabel}</FormLabel>
                      <FormControl>
                        <Input
                          placeholder={idNumberPlaceholder}
                          disabled={isPending}
                          className="h-11"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* 手机号字段 - Requirements: 5.2, 7.5 (触摸区域 44px) */}
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

                {/* 地址字段 - Requirements: 5.2, 7.5 (触摸区域 44px) */}
                <FormField
                  control={form.control}
                  name="address"
                  render={({ field }) => (
                    <FormItem className="lg:col-span-2">
                      <FormLabel>地址</FormLabel>
                      <FormControl>
                        <Input
                          placeholder="请输入地址"
                          disabled={isPending}
                          className="h-11"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* 法定代表人/负责人字段 - Requirements: 5.3 (条件显示，法人/非法人组织必填), 7.5 (触摸区域 44px) */}
                {showLegalRepresentative && (
                  <FormField
                    control={form.control}
                    name="legal_representative"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          {legalRepLabel} <span className="text-destructive">*</span>
                        </FormLabel>
                        <FormControl>
                          <Input
                            placeholder={legalRepPlaceholder}
                            disabled={isPending}
                            className="h-11"
                            {...field}
                          />
                        </FormControl>
                        <FormDescription>
                          {legalRepDescription}
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                )}

                {/* 法定代表人/负责人身份证号字段 - 非必填 */}
                {showLegalRepresentative && (
                  <FormField
                    control={form.control}
                    name="legal_representative_id_number"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          {clientType === 'non_legal_org' ? '负责人身份证号' : '法定代表人身份证号'}
                        </FormLabel>
                        <FormControl>
                          <Input
                            placeholder={clientType === 'non_legal_org' ? '请输入负责人身份证号' : '请输入法定代表人身份证号'}
                            disabled={isPending}
                            className="h-11"
                            {...field}
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                )}
              </div>

              {/* 操作按钮 - Requirements: 5.5, 5.7, 7.5 (触摸区域 44px) */}
              <div className="flex flex-col-reverse gap-3 md:flex-row md:justify-end">
                {/* 取消按钮 - Requirements: 5.7, 7.5 */}
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

                {/* 保存按钮 - Requirements: 5.5, 7.5 */}
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

export default ClientForm
