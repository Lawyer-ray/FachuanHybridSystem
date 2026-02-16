/**
 * RecognitionDetail - 识别详情组件
 * @module features/automation/document-recognition/components/RecognitionDetail
 *
 * 显示文书识别任务的详细信息
 * - 显示任务基本信息（文件名、状态、创建时间）
 * - 根据状态显示不同 UI（处理中/成功/失败）
 * - 集成识别结果和手动绑定
 * - 显示轮询状态指示器
 *
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.10
 */

import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router'
import {
  ArrowLeft,
  Loader2,
  Calendar,
  FileText,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Link2,
  Briefcase,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

import { useRecognitionTask, shouldPoll } from '../hooks/use-recognition-task'
import { useUpdateRecognitionInfo } from '../hooks/use-recognition-mutations'
import { RecognitionResult } from './RecognitionResult'
import { ManualBindingDialog } from './ManualBindingDialog'
import type { DocumentRecognitionTask, RecognitionStatus, UpdateRecognitionInfoRequest } from '../types'

// ============================================================================
// Types
// ============================================================================

export interface RecognitionDetailProps {
  /** 识别任务 ID */
  taskId: number
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * 格式化日期时间
 */
function formatDateTime(dateString: string | null | undefined): string {
  if (!dateString) return '-'
  try {
    const date = new Date(dateString)
    return date.toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return '-'
  }
}

/**
 * 获取状态显示配置
 */
function getStatusConfig(status: RecognitionStatus) {
  const configs: Record<RecognitionStatus, {
    label: string
    variant: 'default' | 'secondary' | 'destructive' | 'outline'
    className: string
    icon: React.ReactNode
  }> = {
    pending: {
      label: '待处理',
      variant: 'secondary',
      className: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
      icon: <AlertCircle className="size-3.5" />,
    },
    processing: {
      label: '处理中',
      variant: 'default',
      className: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
      icon: <Loader2 className="size-3.5 animate-spin" />,
    },
    success: {
      label: '成功',
      variant: 'default',
      className: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
      icon: <CheckCircle2 className="size-3.5" />,
    },
    failed: {
      label: '失败',
      variant: 'destructive',
      className: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
      icon: <XCircle className="size-3.5" />,
    },
  }
  return configs[status]
}

// ============================================================================
// Sub-components
// ============================================================================

/**
 * 骨架屏加载状态
 */
function DetailSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      {/* Header skeleton */}
      <div className="flex items-center gap-4">
        <Skeleton className="h-9 w-9" />
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-6 w-20" />
      </div>

      {/* Info card skeleton */}
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-24" />
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex flex-col gap-1">
                <Skeleton className="h-4 w-16" />
                <Skeleton className="h-5 w-32" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Result card skeleton */}
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-32" />
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * 错误状态组件
 */
interface ErrorStateProps {
  error: Error
  onBack: () => void
}

function ErrorState({ error, onBack }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-12">
      <div className="bg-destructive/10 flex size-16 items-center justify-center rounded-full">
        <XCircle className="text-destructive size-8" />
      </div>
      <div className="text-center">
        <h3 className="text-foreground text-lg font-semibold">加载失败</h3>
        <p className="text-muted-foreground mt-1 text-sm">
          {error.message || '无法加载识别详情，请稍后重试'}
        </p>
      </div>
      <Button variant="outline" onClick={onBack}>
        <ArrowLeft className="mr-2 size-4" />
        返回列表
      </Button>
    </div>
  )
}

/**
 * 轮询状态指示器
 * Requirements: 7.2 - 处理中状态显示轮询指示器
 */
interface PollingIndicatorProps {
  isPolling: boolean
}

function PollingIndicator({ isPolling }: PollingIndicatorProps) {
  if (!isPolling) return null

  return (
    <div className="bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium">
      <Loader2 className="size-3 animate-spin" />
      <span>正在识别中...</span>
    </div>
  )
}

/**
 * 状态徽章组件
 */
interface StatusBadgeProps {
  status: RecognitionStatus
}

function StatusBadge({ status }: StatusBadgeProps) {
  const config = getStatusConfig(status)

  return (
    <Badge className={cn('inline-flex items-center gap-1.5', config.className)}>
      {config.icon}
      {config.label}
    </Badge>
  )
}

/**
 * 信息项组件
 */
interface InfoItemProps {
  icon: React.ReactNode
  label: string
  value: React.ReactNode
  className?: string
}

function InfoItem({ icon, label, value, className }: InfoItemProps) {
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <div className="text-muted-foreground flex items-center gap-1.5 text-xs">
        {icon}
        <span>{label}</span>
      </div>
      <div className="text-foreground text-sm font-medium">{value}</div>
    </div>
  )
}

/**
 * 处理中状态组件
 * Requirements: 7.2 - pending/processing 时显示加载状态
 */
function ProcessingState() {
  return (
    <Card>
      <CardContent className="flex flex-col items-center justify-center py-12">
        <div className="bg-blue-100 dark:bg-blue-900/30 flex size-16 items-center justify-center rounded-full">
          <Loader2 className="size-8 animate-spin text-blue-600 dark:text-blue-400" />
        </div>
        <h3 className="text-foreground mt-4 text-lg font-semibold">正在识别文书</h3>
        <p className="text-muted-foreground mt-2 text-center text-sm">
          系统正在分析文书内容，请稍候...
          <br />
          识别完成后将自动更新结果
        </p>
      </CardContent>
    </Card>
  )
}

/**
 * 失败状态组件
 * Requirements: 7.10 - 失败时显示错误信息
 */
interface FailedStateProps {
  errorMessage: string | null
}

function FailedState({ errorMessage }: FailedStateProps) {
  return (
    <Card className="border-destructive/50">
      <CardHeader>
        <CardTitle className="text-destructive flex items-center gap-2 text-base">
          <XCircle className="size-5" />
          识别失败
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="bg-destructive/10 text-destructive rounded-md p-4 text-sm">
          <strong>错误信息：</strong>
          <p className="mt-1">{errorMessage || '未知错误，请重试或联系管理员'}</p>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * 绑定成功信息组件
 * Requirements: 7.4 - 成功且绑定成功时显示绑定的案件信息
 */
interface BindingSuccessInfoProps {
  task: DocumentRecognitionTask
}

function BindingSuccessInfo({ task }: BindingSuccessInfoProps) {
  return (
    <Card className="border-green-200 dark:border-green-900/50">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base text-green-700 dark:text-green-400">
          <Link2 className="size-5" />
          案件绑定成功
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="bg-green-50 dark:bg-green-900/20 rounded-md p-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <InfoItem
              icon={<Briefcase className="size-3.5 text-green-600 dark:text-green-400" />}
              label="绑定案件"
              value={
                <span className="text-green-700 dark:text-green-300">
                  {task.case_name || '-'}
                </span>
              }
            />
            <InfoItem
              icon={<FileText className="size-3.5 text-green-600 dark:text-green-400" />}
              label="案件 ID"
              value={
                <span className="text-green-700 dark:text-green-300">
                  {task.case_id ?? '-'}
                </span>
              }
            />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * 手动绑定提示组件
 * Requirements: 7.5 - 成功但绑定失败时显示手动绑定界面
 */
interface ManualBindingPromptProps {
  onBindClick: () => void
}

function ManualBindingPrompt({ onBindClick }: ManualBindingPromptProps) {
  return (
    <Card className="border-yellow-200 dark:border-yellow-900/50">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base text-yellow-700 dark:text-yellow-400">
          <AlertCircle className="size-5" />
          需要手动绑定
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="bg-yellow-50 dark:bg-yellow-900/20 rounded-md p-4">
          <p className="text-yellow-800 dark:text-yellow-200 text-sm">
            自动绑定失败，请手动选择要绑定的案件。
          </p>
          <Button
            onClick={onBindClick}
            className="mt-4"
            variant="outline"
          >
            <Link2 className="mr-2 size-4" />
            手动绑定案件
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 识别详情组件
 *
 * Requirements:
 * - 7.1: 显示任务基本信息（文件名、状态、创建时间）
 * - 7.2: 处理中状态显示轮询指示器
 * - 7.3: 成功时显示识别结果
 * - 7.4: 成功且绑定成功时显示绑定的案件信息
 * - 7.5: 成功但绑定失败时显示手动绑定界面
 * - 7.10: 失败时显示错误信息
 *
 * @example
 * ```tsx
 * <RecognitionDetail taskId={123} />
 * ```
 */
export function RecognitionDetail({ taskId }: RecognitionDetailProps) {
  const navigate = useNavigate()

  // ========== State ==========
  const [isEditing, setIsEditing] = useState(false)
  const [bindingDialogOpen, setBindingDialogOpen] = useState(false)

  // ========== 数据查询（带轮询） ==========
  // Requirements: 7.2 - pending/processing 时每 2 秒轮询
  const {
    data: task,
    isLoading,
    error,
    isFetching,
  } = useRecognitionTask(taskId, { enablePolling: true })

  // ========== Mutations ==========
  const updateRecognitionInfo = useUpdateRecognitionInfo()

  // ========== 事件处理 ==========

  /**
   * 返回列表
   */
  const handleBack = useCallback(() => {
    navigate('/admin/automation/document-recognition')
  }, [navigate])

  /**
   * 开始编辑识别结果
   */
  const handleEdit = useCallback(() => {
    setIsEditing(true)
  }, [])

  /**
   * 取消编辑
   */
  const handleCancelEdit = useCallback(() => {
    setIsEditing(false)
  }, [])

  /**
   * 保存识别结果
   * Requirements: 7.9
   */
  const handleSave = useCallback(
    (data: UpdateRecognitionInfoRequest) => {
      updateRecognitionInfo.mutate(
        { taskId, data },
        {
          onSuccess: () => {
            setIsEditing(false)
          },
        }
      )
    },
    [updateRecognitionInfo, taskId]
  )

  /**
   * 打开手动绑定对话框
   */
  const handleOpenBindingDialog = useCallback(() => {
    setBindingDialogOpen(true)
  }, [])

  /**
   * 绑定成功回调
   */
  const handleBindSuccess = useCallback(() => {
    // 绑定成功后对话框会自动关闭，数据会自动刷新
  }, [])

  // ========== 渲染 ==========

  // 加载状态
  if (isLoading) {
    return <DetailSkeleton />
  }

  // 错误状态
  if (error) {
    return <ErrorState error={error} onBack={handleBack} />
  }

  // 数据不存在
  if (!task) {
    return (
      <ErrorState
        error={new Error('识别任务不存在')}
        onBack={handleBack}
      />
    )
  }

  // 判断是否正在轮询
  // Requirements: 7.2
  const isPolling = shouldPoll(task.status) && isFetching
  const isProcessing = task.status === 'pending' || task.status === 'processing'
  const isSuccess = task.status === 'success'
  const isFailed = task.status === 'failed'

  return (
    <div className="flex flex-col gap-6">
      {/* ========== Header Section ========== */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-3">
          {/* 返回按钮 */}
          <Button
            variant="ghost"
            size="icon"
            onClick={handleBack}
            className="shrink-0"
          >
            <ArrowLeft className="size-5" />
            <span className="sr-only">返回</span>
          </Button>

          {/* 标题 */}
          <h1 className="text-foreground text-xl font-semibold sm:text-2xl">
            识别详情
          </h1>

          {/* 状态徽章 */}
          <StatusBadge status={task.status} />

          {/* 轮询指示器 */}
          {/* Requirements: 7.2 */}
          <PollingIndicator isPolling={isPolling} />
        </div>
      </div>

      {/* ========== Basic Info Card ========== */}
      {/* Requirements: 7.1 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">基本信息</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {/* 文件名 */}
            <InfoItem
              icon={<FileText className="size-3.5" />}
              label="文件名"
              value={
                <span className="truncate" title={task.file_name}>
                  {task.file_name}
                </span>
              }
              className="lg:col-span-2"
            />

            {/* 创建时间 */}
            <InfoItem
              icon={<Calendar className="size-3.5" />}
              label="创建时间"
              value={formatDateTime(task.created_at)}
            />

            {/* 更新时间 */}
            <InfoItem
              icon={<Calendar className="size-3.5" />}
              label="更新时间"
              value={formatDateTime(task.updated_at)}
            />
          </div>
        </CardContent>
      </Card>

      {/* ========== Status-based Content ========== */}

      {/* 处理中状态 */}
      {/* Requirements: 7.2 */}
      {isProcessing && <ProcessingState />}

      {/* 失败状态 */}
      {/* Requirements: 7.10 */}
      {isFailed && <FailedState errorMessage={task.error_message} />}

      {/* 成功状态 */}
      {isSuccess && (
        <>
          {/* 识别结果 */}
          {/* Requirements: 7.3 */}
          <RecognitionResult
            task={task}
            onEdit={handleEdit}
            isEditing={isEditing}
            onSave={handleSave}
            onCancel={handleCancelEdit}
          />

          {/* 绑定状态 */}
          {task.binding_success === true ? (
            // Requirements: 7.4 - 绑定成功显示案件信息
            <BindingSuccessInfo task={task} />
          ) : (
            // Requirements: 7.5 - 绑定失败显示手动绑定界面
            <ManualBindingPrompt onBindClick={handleOpenBindingDialog} />
          )}
        </>
      )}

      {/* ========== Manual Binding Dialog ========== */}
      {/* Requirements: 7.5 */}
      <ManualBindingDialog
        open={bindingDialogOpen}
        onOpenChange={setBindingDialogOpen}
        task={task}
        onBindSuccess={handleBindSuccess}
      />
    </div>
  )
}

export default RecognitionDetail
