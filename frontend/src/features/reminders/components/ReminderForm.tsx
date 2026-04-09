/**
 * ReminderForm Component
 * 提醒表单组件
 *
 * 使用 React Hook Form + Zod 验证
 * 支持 create/edit 两种模式
 * 实现字段级错误显示
 * 支持明亮/暗夜主题
 *
 * @module features/reminders/components/ReminderForm
 *
 * Requirements:
 * - 4.1: 用户点击"新建提醒"按钮打开表单对话框
 * - 4.3: 用户提交空的必填字段显示验证错误
 * - 5.1: 编辑时预填充数据
 * - 7.5: 字段验证失败时在对应字段下方显示错误信息
 * - 9.1: 支持明亮模式
 * - 9.2: 支持暗夜模式
 */

import { useEffect, useMemo } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { format, parseISO } from 'date-fns'
import { CalendarIcon, Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
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
import { cn } from '@/lib/utils'

import { reminderFormSchema, type ReminderFormData } from '../schemas'
import type { Reminder, ReminderTypeOption } from '../types'
import { REMINDER_TYPE_LABELS } from '../types'
import { useReminderTypes } from '../hooks/use-reminders'


// ============================================================================
// Types
// ============================================================================

/**
 * 关联选项类型
 */
interface AssociationOption {
  id: number
  label: string
}

/**
 * ReminderForm 组件属性
 */
export interface ReminderFormProps {
  /** 表单模式：创建或编辑 */
  mode: 'create' | 'edit'
  /** 编辑模式下的提醒数据 */
  reminder?: Reminder
  /** 表单提交回调 */
  onSubmit: (data: ReminderFormData) => void
  /** 取消回调 */
  onCancel?: () => void
  /** 是否正在提交 */
  isSubmitting?: boolean
  /** 合同选项列表（可选，用于关联选择） */
  contractOptions?: AssociationOption[]
  /** 案件日志选项列表（可选，用于关联选择） */
  caseLogOptions?: AssociationOption[]
}

/**
 * 关联类型
 */
type AssociationType = 'contract' | 'case_log'

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * 格式化日期时间为 datetime-local input 所需的格式
 */
function formatDateTimeForInput(date: Date | undefined): string {
  if (!date) return ''
  return format(date, "yyyy-MM-dd'T'HH:mm")
}

/**
 * 解析 ISO 日期字符串为 Date 对象
 */
function parseISODate(isoString: string | null): Date | undefined {
  if (!isoString) return undefined
  try {
    return parseISO(isoString)
  } catch {
    return undefined
  }
}

/**
 * 获取默认的提醒类型选项
 */
function getDefaultReminderTypes(): ReminderTypeOption[] {
  return Object.entries(REMINDER_TYPE_LABELS).map(([value, label]) => ({
    value: value as ReminderTypeOption['value'],
    label,
  }))
}


// ============================================================================
// Component
// ============================================================================

/**
 * 提醒表单组件
 *
 * 提供以下功能：
 * - 提醒类型选择
 * - 提醒内容输入（Textarea）
 * - 到期时间选择（DateTime picker）
 * - 关联选择（合同或案件日志二选一）
 * - 字段级错误显示
 * - 支持明亮/暗夜主题
 *
 * Requirements: 4.1, 4.3, 5.1, 7.5, 9.1, 9.2
 */
export function ReminderForm({
  mode,
  reminder,
  onSubmit,
  onCancel,
  isSubmitting = false,
  contractOptions = [],
  caseLogOptions = [],
}: ReminderFormProps) {
  const isEditMode = mode === 'edit'

  // 获取提醒类型列表
  const { data: reminderTypesData } = useReminderTypes()
  const reminderTypes = reminderTypesData ?? getDefaultReminderTypes()

  // ========== Form Setup ==========

  // 计算默认值
  const defaultValues = useMemo(() => {
    if (isEditMode && reminder) {
      // 编辑模式：预填充现有数据 - Requirements: 5.1
      return {
        reminder_type: reminder.reminder_type,
        content: reminder.content,
        due_at: parseISODate(reminder.due_at),
        contract_id: reminder.contract ?? null,
        case_log_id: reminder.case_log ?? null,
        metadata: reminder.metadata ?? {},
      }
    }
    // 创建模式：空表单
    return {
      reminder_type: '',
      content: '',
      due_at: undefined,
      contract_id: null,
      case_log_id: null,
      metadata: {},
    }
  }, [isEditMode, reminder])

  // 初始化表单
  const form = useForm<ReminderFormData>({
    resolver: zodResolver(reminderFormSchema),
    defaultValues,
  })

  // 监听关联字段变化，用于实现二选一逻辑
  const contractId = form.watch('contract_id')
  const caseLogId = form.watch('case_log_id')

  // 计算当前选择的关联类型
  const associationType: AssociationType | null = useMemo(() => {
    if (contractId && contractId !== 0) return 'contract'
    if (caseLogId && caseLogId !== 0) return 'case_log'
    return null
  }, [contractId, caseLogId])

  // ========== Effects ==========

  // 编辑模式下，当 reminder 数据变化时重置表单
  useEffect(() => {
    if (isEditMode && reminder) {
      form.reset({
        reminder_type: reminder.reminder_type,
        content: reminder.content,
        due_at: parseISODate(reminder.due_at),
        contract_id: reminder.contract ?? null,
        case_log_id: reminder.case_log ?? null,
        metadata: reminder.metadata ?? {},
      })
    }
  }, [isEditMode, reminder, form])


  // ========== Event Handlers ==========

  /**
   * 处理关联类型切换
   * 当选择一种关联类型时，清除另一种
   */
  const handleAssociationTypeChange = (type: AssociationType) => {
    if (type === 'contract') {
      form.setValue('case_log_id', null, { shouldValidate: true })
    } else {
      form.setValue('contract_id', null, { shouldValidate: true })
    }
  }

  /**
   * 处理合同选择变更
   */
  const handleContractChange = (value: string) => {
    const numValue = value ? parseInt(value, 10) : null
    form.setValue('contract_id', numValue, { shouldValidate: true })
    if (numValue) {
      form.setValue('case_log_id', null, { shouldValidate: true })
    }
  }

  /**
   * 处理案件日志选择变更
   */
  const handleCaseLogChange = (value: string) => {
    const numValue = value ? parseInt(value, 10) : null
    form.setValue('case_log_id', numValue, { shouldValidate: true })
    if (numValue) {
      form.setValue('contract_id', null, { shouldValidate: true })
    }
  }

  /**
   * 处理日期时间变更
   */
  const handleDateTimeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    if (value) {
      form.setValue('due_at', new Date(value), { shouldValidate: true })
    } else {
      form.setValue('due_at', undefined as unknown as Date, { shouldValidate: true })
    }
  }

  /**
   * 表单提交处理
   */
  const handleFormSubmit = (data: ReminderFormData) => {
    onSubmit(data)
  }


  // ========== Render ==========

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(handleFormSubmit)} className="space-y-6">
        {/* 提醒类型字段 - Requirements: 7.1 */}
        <FormField
          control={form.control}
          name="reminder_type"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                提醒类型 <span className="text-destructive">*</span>
              </FormLabel>
              <Select
                onValueChange={field.onChange}
                value={field.value}
                disabled={isSubmitting}
              >
                <FormControl>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="请选择提醒类型" />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {reminderTypes.map((type) => (
                    <SelectItem key={type.value} value={type.value}>
                      {type.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />

        {/* 提醒内容字段 - Requirements: 7.2 */}
        <FormField
          control={form.control}
          name="content"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                提醒事项 <span className="text-destructive">*</span>
              </FormLabel>
              <FormControl>
                <textarea
                  placeholder="请输入提醒事项内容"
                  disabled={isSubmitting}
                  className={cn(
                    'flex min-h-[100px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs',
                    'placeholder:text-muted-foreground',
                    'focus-visible:outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]',
                    'disabled:cursor-not-allowed disabled:opacity-50',
                    'aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive',
                    'dark:bg-input/30 resize-none'
                  )}
                  {...field}
                />
              </FormControl>
              <FormDescription>最多255字符</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        {/* 到期时间字段 - Requirements: 7.3 */}
        <FormField
          control={form.control}
          name="due_at"
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                到期时间 <span className="text-destructive">*</span>
              </FormLabel>
              <FormControl>
                <div className="relative">
                  <CalendarIcon className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />
                  <Input
                    type="datetime-local"
                    value={formatDateTimeForInput(field.value)}
                    onChange={handleDateTimeChange}
                    disabled={isSubmitting}
                    className={cn(
                      'pl-9',
                      '[&::-webkit-calendar-picker-indicator]:opacity-0',
                      '[&::-webkit-calendar-picker-indicator]:absolute',
                      '[&::-webkit-calendar-picker-indicator]:inset-0',
                      '[&::-webkit-calendar-picker-indicator]:w-full',
                      '[&::-webkit-calendar-picker-indicator]:h-full',
                      '[&::-webkit-calendar-picker-indicator]:cursor-pointer'
                    )}
                  />
                </div>
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />


        {/* 关联选择 - Requirements: 7.4 */}
        <div className="space-y-4">
          <FormLabel>
            关联 <span className="text-destructive">*</span>
          </FormLabel>
          <FormDescription>
            必须且只能关联合同或案件日志之一
          </FormDescription>

          {/* 关联类型选择按钮 */}
          <div className="flex gap-2">
            <Button
              type="button"
              variant={associationType === 'contract' ? 'default' : 'outline'}
              size="sm"
              onClick={() => handleAssociationTypeChange('contract')}
              disabled={isSubmitting}
              className="flex-1"
            >
              关联合同
            </Button>
            <Button
              type="button"
              variant={associationType === 'case_log' ? 'default' : 'outline'}
              size="sm"
              onClick={() => handleAssociationTypeChange('case_log')}
              disabled={isSubmitting}
              className="flex-1"
            >
              关联案件日志
            </Button>
          </div>

          {/* 合同选择 */}
          {(associationType === 'contract' || associationType === null) && (
            <FormField
              control={form.control}
              name="contract_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="sr-only">选择合同</FormLabel>
                  <Select
                    onValueChange={handleContractChange}
                    value={field.value?.toString() ?? ''}
                    disabled={isSubmitting}
                  >
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="请选择关联的合同" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {contractOptions.length > 0 ? (
                        contractOptions.map((option) => (
                          <SelectItem key={option.id} value={option.id.toString()}>
                            {option.label}
                          </SelectItem>
                        ))
                      ) : (
                        <SelectItem value="__placeholder__" disabled>
                          暂无可选合同
                        </SelectItem>
                      )}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
          )}

          {/* 案件日志选择 */}
          {(associationType === 'case_log' || associationType === null) && (
            <FormField
              control={form.control}
              name="case_log_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="sr-only">选择案件日志</FormLabel>
                  <Select
                    onValueChange={handleCaseLogChange}
                    value={field.value?.toString() ?? ''}
                    disabled={isSubmitting}
                  >
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="请选择关联的案件日志" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {caseLogOptions.length > 0 ? (
                        caseLogOptions.map((option) => (
                          <SelectItem key={option.id} value={option.id.toString()}>
                            {option.label}
                          </SelectItem>
                        ))
                      ) : (
                        <SelectItem value="__placeholder__" disabled>
                          暂无可选案件日志
                        </SelectItem>
                      )}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />
          )}
        </div>

        {/* 操作按钮 */}
        <div className="flex flex-col-reverse gap-3 pt-4 sm:flex-row sm:justify-end">
          {onCancel && (
            <Button
              type="button"
              variant="outline"
              onClick={onCancel}
              disabled={isSubmitting}
            >
              取消
            </Button>
          )}
          <Button type="submit" disabled={isSubmitting}>
            {isSubmitting ? (
              <>
                <Loader2 className="mr-2 size-4 animate-spin" />
                {isEditMode ? '保存中...' : '创建中...'}
              </>
            ) : (
              <>{isEditMode ? '保存' : '创建'}</>
            )}
          </Button>
        </div>
      </form>
    </Form>
  )
}

// ============================================================================
// Default Export
// ============================================================================

export default ReminderForm
