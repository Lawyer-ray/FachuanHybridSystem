/**
 * QuoteCreateDialog - 创建询价对话框组件
 * @module features/automation/preservation-quotes/components/QuoteCreateDialog
 *
 * 提供创建财产保全询价的表单对话框
 * - 表单验证（Zod + React Hook Form）
 * - 关联字段选择（企业、类别、凭证）
 * - 提交状态处理
 * - 字段级错误信息显示
 *
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 9.4
 */

import { useCallback, useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
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
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

import { quoteCreateSchema, type QuoteCreateFormData } from '../schemas'
import { useCreateQuote } from '../hooks/use-quote-mutations'
import type { PreservationQuote } from '../types'

// ============================================================================
// Types
// ============================================================================

/**
 * 选项类型
 */
export interface SelectOption {
  value: string
  label: string
}

/**
 * 凭证选项类型（value 为 number）
 */
export interface CredentialOption {
  value: number
  label: string
}

/**
 * QuoteCreateDialog Props
 */
export interface QuoteCreateDialogProps {
  /** 对话框开关 */
  open: boolean
  /** 关闭回调 */
  onOpenChange: (open: boolean) => void
  /** 创建成功回调 */
  onSuccess?: (quote: PreservationQuote) => void
  /** 企业选项列表 */
  corpOptions?: SelectOption[]
  /** 类别选项列表 */
  categoryOptions?: SelectOption[]
  /** 凭证选项列表 */
  credentialOptions?: CredentialOption[]
}

// ============================================================================
// Constants - Mock Data
// ============================================================================

/**
 * 默认企业选项（占位数据）
 */
const DEFAULT_CORP_OPTIONS: SelectOption[] = [
  { value: 'corp_001', label: '示例企业 A' },
  { value: 'corp_002', label: '示例企业 B' },
  { value: 'corp_003', label: '示例企业 C' },
]

/**
 * 默认类别选项（占位数据）
 */
const DEFAULT_CATEGORY_OPTIONS: SelectOption[] = [
  { value: 'cat_001', label: '财产保全' },
  { value: 'cat_002', label: '诉讼保全' },
  { value: 'cat_003', label: '仲裁保全' },
]

/**
 * 默认凭证选项（占位数据）
 */
const DEFAULT_CREDENTIAL_OPTIONS: CredentialOption[] = [
  { value: 1, label: '凭证 1' },
  { value: 2, label: '凭证 2' },
  { value: 3, label: '凭证 3' },
]

// ============================================================================
// Main Component
// ============================================================================

/**
 * 创建询价对话框组件
 *
 * Requirements:
 * - 3.1: 提供创建询价的表单对话框
 * - 3.2: 要求用户输入保全金额（必填，正数）
 * - 3.3: 要求用户选择企业（corp_id，必填）
 * - 3.4: 要求用户选择类别（category_id，必填）
 * - 3.5: 要求用户选择凭证（credential_id，必填）
 * - 3.6: 用户提交有效表单时创建询价任务并显示成功提示
 * - 3.7: 表单验证失败时显示具体的错误信息
 * - 3.8: API 请求失败时显示错误提示并保留表单数据
 * - 9.4: 在表单字段旁显示验证错误信息
 *
 * @example
 * ```tsx
 * const [open, setOpen] = useState(false)
 *
 * <QuoteCreateDialog
 *   open={open}
 *   onOpenChange={setOpen}
 *   onSuccess={(quote) => {
 *     navigate(`/admin/automation/preservation-quotes/${quote.id}`)
 *   }}
 * />
 * ```
 */
export function QuoteCreateDialog({
  open,
  onOpenChange,
  onSuccess,
  corpOptions = DEFAULT_CORP_OPTIONS,
  categoryOptions = DEFAULT_CATEGORY_OPTIONS,
  credentialOptions = DEFAULT_CREDENTIAL_OPTIONS,
}: QuoteCreateDialogProps) {
  // ========== Form Setup ==========
  const form = useForm<QuoteCreateFormData>({
    resolver: zodResolver(quoteCreateSchema),
    defaultValues: {
      preserve_amount: undefined,
      corp_id: '',
      category_id: '',
      credential_id: undefined,
    },
  })

  // ========== Mutation ==========
  // Requirements: 3.6 - 创建询价任务
  const createQuote = useCreateQuote()

  // ========== Effects ==========

  /**
   * 对话框关闭时重置表单
   * 但如果是 API 失败，保留表单数据 (Requirements: 3.8)
   */
  useEffect(() => {
    if (!open && !createQuote.isError) {
      form.reset()
    }
  }, [open, form, createQuote.isError])

  // ========== Event Handlers ==========

  /**
   * 表单提交处理
   * Requirements: 3.6, 3.7
   */
  const handleSubmit = useCallback(
    async (data: QuoteCreateFormData) => {
      createQuote.mutate(data, {
        onSuccess: (quote) => {
          // 关闭对话框
          onOpenChange(false)
          // 重置表单
          form.reset()
          // 调用成功回调
          onSuccess?.(quote)
        },
        // Requirements: 3.8 - API 请求失败时保留表单数据
        // 错误处理在 useCreateQuote 中已经处理（显示 toast）
      })
    },
    [createQuote, onOpenChange, form, onSuccess]
  )

  /**
   * 取消按钮处理
   */
  const handleCancel = useCallback(() => {
    onOpenChange(false)
  }, [onOpenChange])

  // ========== Render ==========

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>创建询价</DialogTitle>
          <DialogDescription>
            填写以下信息创建新的财产保全询价任务
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(handleSubmit)}
            className="space-y-4"
          >
            {/* ========== 保全金额 ========== */}
            {/* Requirements: 3.2, 9.4 */}
            <FormField
              control={form.control}
              name="preserve_amount"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    保全金额 <span className="text-destructive">*</span>
                  </FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      placeholder="请输入保全金额"
                      {...field}
                      value={field.value ?? ''}
                      onChange={(e) => {
                        const value = e.target.value
                        field.onChange(value === '' ? undefined : Number(value))
                      }}
                    />
                  </FormControl>
                  {/* Requirements: 3.7, 9.4 - 字段级错误信息 */}
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* ========== 企业选择 ========== */}
            {/* Requirements: 3.3, 9.4 */}
            <FormField
              control={form.control}
              name="corp_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    企业 <span className="text-destructive">*</span>
                  </FormLabel>
                  <Select
                    onValueChange={field.onChange}
                    value={field.value}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="请选择企业" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {corpOptions.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {/* Requirements: 3.7, 9.4 - 字段级错误信息 */}
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* ========== 类别选择 ========== */}
            {/* Requirements: 3.4, 9.4 */}
            <FormField
              control={form.control}
              name="category_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    类别 <span className="text-destructive">*</span>
                  </FormLabel>
                  <Select
                    onValueChange={field.onChange}
                    value={field.value}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="请选择类别" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {categoryOptions.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {/* Requirements: 3.7, 9.4 - 字段级错误信息 */}
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* ========== 凭证选择 ========== */}
            {/* Requirements: 3.5, 9.4 */}
            <FormField
              control={form.control}
              name="credential_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    凭证 <span className="text-destructive">*</span>
                  </FormLabel>
                  <Select
                    onValueChange={(value) => field.onChange(Number(value))}
                    value={field.value?.toString() ?? ''}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="请选择凭证" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {credentialOptions.map((option) => (
                        <SelectItem
                          key={option.value}
                          value={option.value.toString()}
                        >
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {/* Requirements: 3.7, 9.4 - 字段级错误信息 */}
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* ========== 操作按钮 ========== */}
            <DialogFooter className="pt-4">
              <Button
                type="button"
                variant="outline"
                onClick={handleCancel}
                disabled={createQuote.isPending}
              >
                取消
              </Button>
              <Button type="submit" disabled={createQuote.isPending}>
                {createQuote.isPending ? (
                  <>
                    <Loader2 className="mr-2 size-4 animate-spin" />
                    创建中...
                  </>
                ) : (
                  '创建'
                )}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

export default QuoteCreateDialog
