/**
 * ReminderFormDialog Component
 * 提醒表单对话框组件
 *
 * 封装 Dialog + ReminderForm
 * 处理打开/关闭状态
 * 显示成功/失败提示
 *
 * @module features/reminders/components/ReminderFormDialog
 *
 * Requirements:
 * - 4.1: 用户点击"新建提醒"按钮打开表单对话框
 * - 4.4: 创建成功关闭对话框并显示成功提示
 * - 4.5: 创建失败显示错误提示并保留表单数据
 * - 5.3: 更新成功关闭对话框并显示成功提示
 * - 5.4: 更新失败显示错误提示并保留表单数据
 */

import { useCallback } from 'react'
import { toast } from 'sonner'

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

import { ReminderForm } from './ReminderForm'
import { useReminderMutations } from '../hooks/use-reminder-mutations'
import type { Reminder, ReminderInput } from '../types'
import type { ReminderFormData } from '../schemas'

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
 * ReminderFormDialog 组件属性
 */
export interface ReminderFormDialogProps {
  /** 对话框打开状态 */
  open: boolean
  /** 对话框状态变更回调 */
  onOpenChange: (open: boolean) => void
  /** 表单模式：创建或编辑 */
  mode: 'create' | 'edit'
  /** 编辑模式下的提醒数据 */
  reminder?: Reminder
  /** 操作成功回调 */
  onSuccess?: () => void
  /** 合同选项列表（可选，用于关联选择） */
  contractOptions?: AssociationOption[]
  /** 案件日志选项列表（可选，用于关联选择） */
  caseLogOptions?: AssociationOption[]
}

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * 将表单数据转换为 API 输入格式
 */
function formDataToInput(data: ReminderFormData): ReminderInput {
  return {
    reminder_type: data.reminder_type as ReminderInput['reminder_type'],
    content: data.content,
    due_at: data.due_at.toISOString(),
    contract_id: data.contract_id ?? null,
    case_log_id: data.case_log_id ?? null,
    metadata: data.metadata ?? {},
  }
}

// ============================================================================
// Component
// ============================================================================

/**
 * 提醒表单对话框组件
 *
 * 提供以下功能：
 * - 封装 Dialog + ReminderForm
 * - 处理创建和编辑两种模式
 * - 成功时关闭对话框并显示成功提示
 * - 失败时显示错误提示并保留表单数据
 *
 * Requirements: 4.1, 4.4, 4.5, 5.3, 5.4
 */
export function ReminderFormDialog({
  open,
  onOpenChange,
  mode,
  reminder,
  onSuccess,
  contractOptions = [],
  caseLogOptions = [],
}: ReminderFormDialogProps) {
  const { createMutation, updateMutation } = useReminderMutations()

  const isEditMode = mode === 'edit'
  const isSubmitting = createMutation.isPending || updateMutation.isPending

  /**
   * 处理表单提交
   * - 创建模式：调用 createMutation
   * - 编辑模式：调用 updateMutation
   * - 成功：关闭对话框，显示成功提示 (Requirements: 4.4, 5.3)
   * - 失败：显示错误提示，保留表单数据 (Requirements: 4.5, 5.4)
   */
  const handleSubmit = useCallback(
    (data: ReminderFormData) => {
      const input = formDataToInput(data)

      if (isEditMode && reminder) {
        // 编辑模式 - Requirements: 5.3, 5.4
        updateMutation.mutate(
          { id: reminder.id, data: input },
          {
            onSuccess: () => {
              toast.success('提醒更新成功')
              onOpenChange(false)
              onSuccess?.()
            },
            onError: (error) => {
              toast.error(`更新失败：${error.message || '请稍后重试'}`)
              // 保留表单数据，不关闭对话框
            },
          }
        )
      } else {
        // 创建模式 - Requirements: 4.4, 4.5
        createMutation.mutate(input, {
          onSuccess: () => {
            toast.success('提醒创建成功')
            onOpenChange(false)
            onSuccess?.()
          },
          onError: (error) => {
            toast.error(`创建失败：${error.message || '请稍后重试'}`)
            // 保留表单数据，不关闭对话框
          },
        })
      }
    },
    [isEditMode, reminder, createMutation, updateMutation, onOpenChange, onSuccess]
  )

  /**
   * 处理取消操作
   */
  const handleCancel = useCallback(() => {
    onOpenChange(false)
  }, [onOpenChange])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {isEditMode ? '编辑提醒' : '新建提醒'}
          </DialogTitle>
          <DialogDescription>
            {isEditMode
              ? '修改提醒信息，完成后点击保存'
              : '填写提醒信息，创建新的重要日期提醒'}
          </DialogDescription>
        </DialogHeader>

        <ReminderForm
          mode={mode}
          reminder={reminder}
          onSubmit={handleSubmit}
          onCancel={handleCancel}
          isSubmitting={isSubmitting}
          contractOptions={contractOptions}
          caseLogOptions={caseLogOptions}
        />
      </DialogContent>
    </Dialog>
  )
}

// ============================================================================
// Default Export
// ============================================================================

export default ReminderFormDialog
