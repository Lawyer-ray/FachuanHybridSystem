/**
 * ReminderList Component
 * 提醒列表组件
 *
 * 表格布局显示提醒列表，集成筛选、状态指示、加载/空/错误状态
 * 支持明亮/暗夜主题和响应式布局
 *
 * @module features/reminders/components/ReminderList
 *
 * Requirements:
 * - 1.1: 展示提醒列表表格，包含类型、提醒事项、到期时间、关联、操作列
 * - 1.2: 显示骨架屏加载状态
 * - 1.3: 显示空状态提示并引导用户创建提醒
 * - 1.4: 显示错误提示并提供重试按钮
 * - 2.1-2.4: 状态视觉指示（红色/橙色/默认）
 * - 8.1-8.3: 响应式布局
 * - 9.1-9.3: 主题支持
 */

import { useState, useMemo, useCallback } from 'react'
import { format } from 'date-fns'
import { zhCN } from 'date-fns/locale'
import {
  AlertCircle,
  CalendarClock,
  Edit,
  FileText,
  Plus,
  RefreshCw,
  Trash2,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'

import { ReminderFilters } from './ReminderFilters'
import { ReminderFormDialog } from './ReminderFormDialog'
import { DeleteConfirmDialog } from './DeleteConfirmDialog'
import { useReminders, useReminderTypes } from '../hooks/use-reminders'
import { getReminderStatus, getStatusStyles, filterReminders } from '../utils'
import { REMINDER_TYPE_LABELS } from '../types'
import type { Reminder, ReminderFilters as ReminderFiltersType } from '../types'

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
 * ReminderList 组件属性
 */
export interface ReminderListProps {
  /** 合同选项列表（可选，用于关联选择） */
  contractOptions?: AssociationOption[]
  /** 案件日志选项列表（可选，用于关联选择） */
  caseLogOptions?: AssociationOption[]
}

// ============================================================================
// Sub-components
// ============================================================================

/**
 * 加载骨架屏组件
 * Requirement 1.2: 显示骨架屏加载状态
 */
function LoadingSkeleton() {
  return (
    <div className="space-y-4" data-testid="loading-skeleton">
      {/* 筛选区域骨架 */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:flex-wrap">
        <div className="flex flex-col gap-1.5">
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-10 w-full sm:w-[180px]" />
        </div>
        <div className="flex flex-col gap-1.5">
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-10 w-full sm:w-[160px]" />
        </div>
        <div className="flex flex-col gap-1.5">
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-10 w-full sm:w-[160px]" />
        </div>
      </div>

      {/* 表格骨架 */}
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>类型</TableHead>
              <TableHead className="hidden sm:table-cell">提醒事项</TableHead>
              <TableHead>到期时间</TableHead>
              <TableHead className="hidden md:table-cell">关联</TableHead>
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {Array.from({ length: 5 }).map((_, index) => (
              <TableRow key={index}>
                <TableCell>
                  <Skeleton className="h-5 w-24" />
                </TableCell>
                <TableCell className="hidden sm:table-cell">
                  <Skeleton className="h-5 w-48" />
                </TableCell>
                <TableCell>
                  <Skeleton className="h-5 w-32" />
                </TableCell>
                <TableCell className="hidden md:table-cell">
                  <Skeleton className="h-5 w-20" />
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-2">
                    <Skeleton className="h-8 w-8" />
                    <Skeleton className="h-8 w-8" />
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

/**
 * 空状态组件
 * Requirement 1.3: 显示空状态提示并引导用户创建提醒
 */
function EmptyState({ onCreateClick }: { onCreateClick: () => void }) {
  return (
    <div
      className="flex flex-col items-center justify-center py-12 px-4"
      data-testid="empty-state"
    >
      <div className="rounded-full bg-muted p-4 mb-4">
        <CalendarClock className="size-8 text-muted-foreground" />
      </div>
      <h3 className="text-lg font-medium text-foreground mb-2">暂无提醒</h3>
      <p className="text-sm text-muted-foreground text-center mb-6 max-w-sm">
        您还没有创建任何重要日期提醒。创建提醒以跟踪关键时间节点。
      </p>
      <Button onClick={onCreateClick} className="gap-2">
        <Plus className="size-4" />
        新建提醒
      </Button>
    </div>
  )
}

/**
 * 错误状态组件
 * Requirement 1.4: 显示错误提示并提供重试按钮
 */
function ErrorState({
  error,
  onRetry,
}: {
  error: Error
  onRetry: () => void
}) {
  return (
    <div
      className="flex flex-col items-center justify-center py-12 px-4"
      data-testid="error-state"
    >
      <div className="rounded-full bg-destructive/10 p-4 mb-4">
        <AlertCircle className="size-8 text-destructive" />
      </div>
      <h3 className="text-lg font-medium text-foreground mb-2">加载失败</h3>
      <p className="text-sm text-muted-foreground text-center mb-6 max-w-sm">
        {error.message || '无法加载提醒列表，请稍后重试。'}
      </p>
      <Button onClick={onRetry} variant="outline" className="gap-2">
        <RefreshCw className="size-4" />
        重试
      </Button>
    </div>
  )
}

/**
 * 提醒行组件
 * Requirements: 1.1, 2.1-2.4
 */
function ReminderRow({
  reminder,
  onEdit,
  onDelete,
}: {
  reminder: Reminder
  onEdit: (reminder: Reminder) => void
  onDelete: (reminder: Reminder) => void
}) {
  const status = getReminderStatus(reminder.due_at)
  const statusStyles = getStatusStyles(status)

  // 格式化到期时间
  const formattedDueAt = reminder.due_at
    ? format(new Date(reminder.due_at), 'yyyy-MM-dd HH:mm', { locale: zhCN })
    : '-'

  // 获取关联信息
  const association = reminder.contract
    ? `合同 #${reminder.contract}`
    : reminder.case_log
      ? `案件 #${reminder.case_log}`
      : '-'

  return (
    <TableRow className={cn('border-l-4', statusStyles)}>
      {/* 类型列 */}
      <TableCell className="font-medium">
        <span className="inline-flex items-center">
          {REMINDER_TYPE_LABELS[reminder.reminder_type] || reminder.reminder_type}
        </span>
        {/* 移动端显示提醒事项 */}
        <div className="sm:hidden mt-1 text-sm text-muted-foreground line-clamp-2">
          {reminder.content}
        </div>
      </TableCell>

      {/* 提醒事项列 - 桌面端显示 */}
      <TableCell className="hidden sm:table-cell max-w-xs">
        <span className="line-clamp-2">{reminder.content}</span>
      </TableCell>

      {/* 到期时间列 */}
      <TableCell>
        <div className="flex items-center gap-1.5">
          <CalendarClock className="size-4 text-muted-foreground shrink-0" />
          <span className={cn(
            status === 'overdue' && 'text-red-600 dark:text-red-400 font-medium',
            status === 'upcoming' && 'text-amber-600 dark:text-amber-400 font-medium'
          )}>
            {formattedDueAt}
          </span>
        </div>
      </TableCell>

      {/* 关联列 - 中等及以上屏幕显示 */}
      <TableCell className="hidden md:table-cell">
        <div className="flex items-center gap-1.5">
          <FileText className="size-4 text-muted-foreground shrink-0" />
          <span className="text-muted-foreground">{association}</span>
        </div>
      </TableCell>

      {/* 操作列 */}
      <TableCell className="text-right">
        <div className="flex justify-end gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onEdit(reminder)}
            className="size-8"
            title="编辑"
          >
            <Edit className="size-4" />
            <span className="sr-only">编辑</span>
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => onDelete(reminder)}
            className="size-8 text-destructive hover:text-destructive hover:bg-destructive/10"
            title="删除"
          >
            <Trash2 className="size-4" />
            <span className="sr-only">删除</span>
          </Button>
        </div>
      </TableCell>
    </TableRow>
  )
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 提醒列表组件
 *
 * 提供以下功能：
 * - 表格布局显示提醒列表 (Requirement 1.1)
 * - 骨架屏加载状态 (Requirement 1.2)
 * - 空状态提示 (Requirement 1.3)
 * - 错误状态和重试 (Requirement 1.4)
 * - 状态视觉指示 (Requirements 2.1-2.4)
 * - 筛选功能集成 (Requirements 3.1-3.4)
 * - 编辑/删除操作 (Requirements 5.1, 6.1)
 * - 响应式布局 (Requirements 8.1-8.3)
 * - 主题支持 (Requirements 9.1-9.3)
 */
export function ReminderList({
  contractOptions = [],
  caseLogOptions = [],
}: ReminderListProps) {
  // ========== State ==========
  const [filters, setFilters] = useState<ReminderFiltersType>({})
  const [formDialogOpen, setFormDialogOpen] = useState(false)
  const [formMode, setFormMode] = useState<'create' | 'edit'>('create')
  const [selectedReminder, setSelectedReminder] = useState<Reminder | undefined>()
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [reminderToDelete, setReminderToDelete] = useState<Reminder | null>(null)

  // ========== Queries ==========
  const {
    data: reminders = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useReminders()

  const { data: reminderTypes = [] } = useReminderTypes()

  // ========== Computed ==========
  // 应用前端筛选
  const filteredReminders = useMemo(() => {
    return filterReminders(reminders, filters)
  }, [reminders, filters])

  // ========== Handlers ==========
  const handleCreateClick = useCallback(() => {
    setFormMode('create')
    setSelectedReminder(undefined)
    setFormDialogOpen(true)
  }, [])

  const handleEditClick = useCallback((reminder: Reminder) => {
    setFormMode('edit')
    setSelectedReminder(reminder)
    setFormDialogOpen(true)
  }, [])

  const handleDeleteClick = useCallback((reminder: Reminder) => {
    setReminderToDelete(reminder)
    setDeleteDialogOpen(true)
  }, [])

  const handleFormSuccess = useCallback(() => {
    setFormDialogOpen(false)
    setSelectedReminder(undefined)
  }, [])

  const handleDeleteSuccess = useCallback(() => {
    setDeleteDialogOpen(false)
    setReminderToDelete(null)
  }, [])

  const handleRetry = useCallback(() => {
    refetch()
  }, [refetch])

  // ========== Render ==========

  // 加载状态
  if (isLoading) {
    return <LoadingSkeleton />
  }

  // 错误状态
  if (isError && error) {
    return <ErrorState error={error} onRetry={handleRetry} />
  }

  return (
    <div className="space-y-4">
      {/* 顶部操作栏 */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        {/* 筛选组件 */}
        <ReminderFilters
          filters={filters}
          onFiltersChange={setFilters}
          reminderTypes={reminderTypes}
        />

        {/* 新建按钮 */}
        <Button onClick={handleCreateClick} className="gap-2 shrink-0">
          <Plus className="size-4" />
          新建提醒
        </Button>
      </div>

      {/* 列表内容 */}
      {filteredReminders.length === 0 ? (
        <EmptyState onCreateClick={handleCreateClick} />
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>类型</TableHead>
                <TableHead className="hidden sm:table-cell">提醒事项</TableHead>
                <TableHead>到期时间</TableHead>
                <TableHead className="hidden md:table-cell">关联</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredReminders.map((reminder) => (
                <ReminderRow
                  key={reminder.id}
                  reminder={reminder}
                  onEdit={handleEditClick}
                  onDelete={handleDeleteClick}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* 表单对话框 */}
      <ReminderFormDialog
        open={formDialogOpen}
        onOpenChange={setFormDialogOpen}
        mode={formMode}
        reminder={selectedReminder}
        onSuccess={handleFormSuccess}
        contractOptions={contractOptions}
        caseLogOptions={caseLogOptions}
      />

      {/* 删除确认对话框 */}
      <DeleteConfirmDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        reminder={reminderToDelete}
        onSuccess={handleDeleteSuccess}
      />
    </div>
  )
}

// ============================================================================
// Default Export
// ============================================================================

export default ReminderList
