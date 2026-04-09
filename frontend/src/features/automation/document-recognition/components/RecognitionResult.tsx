/**
 * RecognitionResult Component
 *
 * 识别结果展示组件
 * - 显示文书类型、案号、关键时间、置信度
 * - 支持编辑模式
 * - 置信度以百分比和视觉指示器显示
 * - 处理 null 值显示占位符
 *
 * Requirements: 7.3, 7.9
 */

import { useCallback } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import {
  FileText,
  Hash,
  Calendar,
  Percent,
  Pencil,
  Save,
  X,
} from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { cn } from '@/lib/utils'

import { updateRecognitionInfoSchema, type UpdateRecognitionInfoFormData } from '../schemas'
import type { DocumentRecognitionTask, UpdateRecognitionInfoRequest } from '../types'

// ============================================================================
// Types
// ============================================================================

export interface RecognitionResultProps {
  /** 识别任务数据 */
  task: DocumentRecognitionTask
  /** 编辑按钮点击回调 */
  onEdit?: () => void
  /** 是否处于编辑模式 */
  isEditing?: boolean
  /** 保存回调 */
  onSave?: (data: UpdateRecognitionInfoRequest) => void
  /** 取消编辑回调 */
  onCancel?: () => void
}

// ============================================================================
// Constants
// ============================================================================

/** 置信度等级阈值 */
const CONFIDENCE_THRESHOLDS = {
  HIGH: 0.8,
  MEDIUM: 0.5,
} as const

// ============================================================================
// Sub-components
// ============================================================================

/**
 * 置信度指示器组件
 * 显示置信度百分比和视觉进度条
 */
interface ConfidenceIndicatorProps {
  /** 置信度值 (0-1) */
  confidence: number | null
}

function ConfidenceIndicator({ confidence }: ConfidenceIndicatorProps) {
  if (confidence === null) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground text-sm">-</span>
      </div>
    )
  }

  const percentage = Math.round(confidence * 100)

  // 根据置信度确定颜色
  const getConfidenceColor = (value: number) => {
    if (value >= CONFIDENCE_THRESHOLDS.HIGH) {
      return {
        bg: 'bg-green-500',
        text: 'text-green-600 dark:text-green-400',
        badge: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
      }
    }
    if (value >= CONFIDENCE_THRESHOLDS.MEDIUM) {
      return {
        bg: 'bg-yellow-500',
        text: 'text-yellow-600 dark:text-yellow-400',
        badge: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
      }
    }
    return {
      bg: 'bg-red-500',
      text: 'text-red-600 dark:text-red-400',
      badge: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
    }
  }

  const colors = getConfidenceColor(confidence)

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <Badge className={cn('text-xs font-medium', colors.badge)}>
          {percentage}%
        </Badge>
        <span className={cn('text-xs', colors.text)}>
          {confidence >= CONFIDENCE_THRESHOLDS.HIGH
            ? '高置信度'
            : confidence >= CONFIDENCE_THRESHOLDS.MEDIUM
              ? '中置信度'
              : '低置信度'}
        </span>
      </div>
      {/* 进度条 */}
      <div className="bg-muted h-1.5 w-full overflow-hidden rounded-full">
        <div
          className={cn('h-full rounded-full transition-all', colors.bg)}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  )
}

/**
 * 信息项组件 - 只读模式
 */
interface InfoItemProps {
  icon: React.ReactNode
  label: string
  value: React.ReactNode
  className?: string
}

function InfoItem({ icon, label, value, className }: InfoItemProps) {
  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <div className="text-muted-foreground flex items-center gap-1.5 text-xs">
        {icon}
        <span>{label}</span>
      </div>
      <div className="text-foreground text-sm font-medium">{value}</div>
    </div>
  )
}

/**
 * 编辑表单组件
 */
interface EditFormProps {
  task: DocumentRecognitionTask
  onSave: (data: UpdateRecognitionInfoRequest) => void
  onCancel: () => void
}

function EditForm({ task, onSave, onCancel }: EditFormProps) {
  const form = useForm<UpdateRecognitionInfoFormData>({
    resolver: zodResolver(updateRecognitionInfoSchema),
    defaultValues: {
      document_type: task.document_type ?? '',
      key_time: task.key_time ?? '',
    },
  })

  const handleSubmit = useCallback(
    (data: UpdateRecognitionInfoFormData) => {
      // 只提交有值的字段
      const payload: UpdateRecognitionInfoRequest = {}
      if (data.document_type) {
        payload.document_type = data.document_type
      }
      if (data.key_time) {
        payload.key_time = data.key_time
      }
      onSave(payload)
    },
    [onSave]
  )

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          {/* 文书类型 */}
          <FormField
            control={form.control}
            name="document_type"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-muted-foreground flex items-center gap-1.5 text-xs">
                  <FileText className="size-3.5" />
                  文书类型
                </FormLabel>
                <FormControl>
                  <Input
                    placeholder="请输入文书类型"
                    {...field}
                    className="h-9"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* 关键时间 */}
          <FormField
            control={form.control}
            name="key_time"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-muted-foreground flex items-center gap-1.5 text-xs">
                  <Calendar className="size-3.5" />
                  关键时间
                </FormLabel>
                <FormControl>
                  <Input
                    placeholder="请输入关键时间"
                    {...field}
                    className="h-9"
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        {/* 只读字段：案号和置信度 */}
        <div className="grid gap-4 sm:grid-cols-2">
          <InfoItem
            icon={<Hash className="size-3.5" />}
            label="案号"
            value={task.case_number ?? <span className="text-muted-foreground">未识别</span>}
          />
          <div className="flex flex-col gap-1.5">
            <div className="text-muted-foreground flex items-center gap-1.5 text-xs">
              <Percent className="size-3.5" />
              <span>置信度</span>
            </div>
            <ConfidenceIndicator confidence={task.confidence} />
          </div>
        </div>

        {/* 操作按钮 */}
        <div className="flex items-center justify-end gap-2 pt-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onCancel}
          >
            <X className="mr-1.5 size-4" />
            取消
          </Button>
          <Button type="submit" size="sm">
            <Save className="mr-1.5 size-4" />
            保存
          </Button>
        </div>
      </form>
    </Form>
  )
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 识别结果展示组件
 *
 * Requirements:
 * - 7.3: 显示识别结果（文书类型、案号、关键时间、置信度）
 * - 7.9: 允许用户修改识别结果（文书类型、关键时间）
 *
 * @example
 * ```tsx
 * // 只读模式
 * <RecognitionResult task={task} onEdit={() => setIsEditing(true)} />
 *
 * // 编辑模式
 * <RecognitionResult
 *   task={task}
 *   isEditing={true}
 *   onSave={handleSave}
 *   onCancel={() => setIsEditing(false)}
 * />
 * ```
 */
export function RecognitionResult({
  task,
  onEdit,
  isEditing = false,
  onSave,
  onCancel,
}: RecognitionResultProps) {
  // ========== 渲染 ==========

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
        <CardTitle className="text-base font-semibold">识别结果</CardTitle>
        {/* 编辑按钮 - 只在非编辑模式且有 onEdit 回调时显示 */}
        {!isEditing && onEdit && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onEdit}
            className="h-8 px-2"
          >
            <Pencil className="mr-1.5 size-4" />
            编辑
          </Button>
        )}
      </CardHeader>

      <CardContent>
        {isEditing && onSave && onCancel ? (
          // 编辑模式 - Requirements: 7.9
          <EditForm task={task} onSave={onSave} onCancel={onCancel} />
        ) : (
          // 只读模式 - Requirements: 7.3
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {/* 文书类型 */}
            <InfoItem
              icon={<FileText className="size-3.5" />}
              label="文书类型"
              value={
                task.document_type ?? (
                  <span className="text-muted-foreground">未识别</span>
                )
              }
            />

            {/* 案号 */}
            <InfoItem
              icon={<Hash className="size-3.5" />}
              label="案号"
              value={
                task.case_number ?? (
                  <span className="text-muted-foreground">未识别</span>
                )
              }
            />

            {/* 关键时间 */}
            <InfoItem
              icon={<Calendar className="size-3.5" />}
              label="关键时间"
              value={
                task.key_time ?? (
                  <span className="text-muted-foreground">未识别</span>
                )
              }
            />

            {/* 置信度 */}
            <div className="flex flex-col gap-1.5">
              <div className="text-muted-foreground flex items-center gap-1.5 text-xs">
                <Percent className="size-3.5" />
                <span>置信度</span>
              </div>
              <ConfidenceIndicator confidence={task.confidence} />
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export default RecognitionResult
