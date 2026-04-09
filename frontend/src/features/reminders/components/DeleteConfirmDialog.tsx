/**
 * DeleteConfirmDialog Component
 * 删除确认对话框组件
 *
 * 显示删除确认对话框，包含确认/取消按钮
 * 处理删除操作并显示成功/失败反馈
 *
 * @module features/reminders/components/DeleteConfirmDialog
 *
 * Requirements:
 * - 6.1: 用户点击删除按钮显示确认对话框
 * - 6.3: 用户取消删除关闭确认对话框
 * - 6.4: 删除成功显示成功提示
 * - 6.5: 删除失败显示错误提示
 */

import { useCallback } from 'react'
import { toast } from 'sonner'
import { Trash2 } from 'lucide-react'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

import { useReminderMutations } from '../hooks/use-reminder-mutations'
import type { Reminder } from '../types'

// ============================================================================
// Types
// ============================================================================

/**
 * DeleteConfirmDialog 组件属性
 */
export interface DeleteConfirmDialogProps {
  /** 对话框打开状态 */
  open: boolean
  /** 对话框状态变更回调 */
  onOpenChange: (open: boolean) => void
  /** 要删除的提醒数据 */
  reminder: Reminder | null
  /** 删除成功回调 */
  onSuccess?: () => void
}

// ============================================================================
// Component
// ============================================================================

/**
 * 删除确认对话框组件
 *
 * 提供以下功能：
 * - 显示删除确认对话框 (Requirement 6.1)
 * - 确认/取消按钮 (Requirement 6.3)
 * - 删除成功显示成功提示 (Requirement 6.4)
 * - 删除失败显示错误提示 (Requirement 6.5)
 *
 * Requirements: 6.1, 6.3, 6.4, 6.5
 */
export function DeleteConfirmDialog({
  open,
  onOpenChange,
  reminder,
  onSuccess,
}: DeleteConfirmDialogProps) {
  const { deleteMutation } = useReminderMutations()

  const isDeleting = deleteMutation.isPending

  /**
   * 处理确认删除
   * - 调用 deleteMutation 删除提醒
   * - 成功：关闭对话框，显示成功提示 (Requirement 6.4)
   * - 失败：显示错误提示 (Requirement 6.5)
   */
  const handleConfirmDelete = useCallback(() => {
    if (!reminder) return

    deleteMutation.mutate(reminder.id, {
      onSuccess: () => {
        // Requirement 6.4: 删除成功显示成功提示
        toast.success('提醒删除成功')
        onOpenChange(false)
        onSuccess?.()
      },
      onError: (error) => {
        // Requirement 6.5: 删除失败显示错误提示
        toast.error(`删除失败：${error.message || '请稍后重试'}`)
      },
    })
  }, [reminder, deleteMutation, onOpenChange, onSuccess])

  /**
   * 处理取消删除
   * Requirement 6.3: 用户取消删除关闭确认对话框
   */
  const handleCancel = useCallback(() => {
    onOpenChange(false)
  }, [onOpenChange])

  // 如果没有提醒数据，不渲染对话框
  if (!reminder) return null

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
            <Trash2 className="size-6" />
          </div>
          <AlertDialogTitle className="text-center">确认删除提醒</AlertDialogTitle>
          <AlertDialogDescription className="text-center">
            您确定要删除提醒「{reminder.content}」吗？此操作无法撤销。
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter className="sm:justify-center">
          {/* Requirement 6.3: 取消按钮 */}
          <AlertDialogCancel onClick={handleCancel} disabled={isDeleting}>
            取消
          </AlertDialogCancel>
          {/* Requirement 6.1: 确认按钮 */}
          <AlertDialogAction
            onClick={handleConfirmDelete}
            disabled={isDeleting}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {isDeleting ? '删除中...' : '确认删除'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

// ============================================================================
// Default Export
// ============================================================================

export default DeleteConfirmDialog
