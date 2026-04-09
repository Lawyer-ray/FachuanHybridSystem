/**
 * QuoteDetail - 询价详情组件
 * @module features/automation/preservation-quotes/components/QuoteDetail
 *
 * 显示询价任务的详细信息
 * - 显示任务基本信息（保全金额、状态、时间信息）
 * - 集成保险报价表格
 * - 实现执行/重试按钮逻辑
 * - 显示轮询状态指示器
 *
 * Requirements: 4.1, 4.2, 4.4, 4.5, 4.8, 4.9
 */

import { useCallback } from 'react'
import { useNavigate } from 'react-router'
import {
  ArrowLeft,
  Play,
  RefreshCw,
  Loader2,
  Calendar,
  Clock,
  CheckCircle2,
  XCircle,
  Banknote,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

import { useQuote, shouldPoll } from '../hooks/use-quote'
import { useExecuteQuote, useRetryQuote } from '../hooks/use-quote-mutations'
import { QuoteStatusBadge } from './QuoteStatusBadge'
import { InsuranceQuoteTable } from './InsuranceQuoteTable'
import type { PreservationQuote } from '../types'

// ============================================================================
// Types
// ============================================================================

export interface QuoteDetailProps {
  /** 询价任务 ID */
  quoteId: number
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * 格式化金额
 */
function formatAmount(amount: string | number): string {
  const num = typeof amount === 'string' ? parseFloat(amount) : amount
  if (isNaN(num)) return '-'
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num)
}

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
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex flex-col gap-1">
                <Skeleton className="h-4 w-16" />
                <Skeleton className="h-5 w-32" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Table skeleton */}
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-32" />
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full" />
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
          {error.message || '无法加载询价详情，请稍后重试'}
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
 * 当任务正在执行时显示
 */
interface PollingIndicatorProps {
  isPolling: boolean
}

function PollingIndicator({ isPolling }: PollingIndicatorProps) {
  if (!isPolling) return null

  return (
    <div className="bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 inline-flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium">
      <Loader2 className="size-3 animate-spin" />
      <span>正在获取最新状态...</span>
    </div>
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
 * 操作按钮组件
 * Requirements: 4.4, 4.5, 4.8, 4.9
 */
interface ActionButtonsProps {
  quote: PreservationQuote
  onExecute: () => void
  onRetry: () => void
  isExecuting: boolean
  isRetrying: boolean
}

function ActionButtons({
  quote,
  onExecute,
  onRetry,
  isExecuting,
  isRetrying,
}: ActionButtonsProps) {
  const { status } = quote

  // Requirements: 4.4 - 任务状态为 pending 时显示"执行询价"按钮
  if (status === 'pending') {
    return (
      <Button onClick={onExecute} disabled={isExecuting}>
        {isExecuting ? (
          <>
            <Loader2 className="mr-2 size-4 animate-spin" />
            执行中...
          </>
        ) : (
          <>
            <Play className="mr-2 size-4" />
            执行询价
          </>
        )}
      </Button>
    )
  }

  // Requirements: 4.8 - 任务失败时显示"重试"按钮
  if (status === 'failed') {
    return (
      <Button onClick={onRetry} disabled={isRetrying} variant="outline">
        {isRetrying ? (
          <>
            <Loader2 className="mr-2 size-4 animate-spin" />
            重试中...
          </>
        ) : (
          <>
            <RefreshCw className="mr-2 size-4" />
            重试
          </>
        )}
      </Button>
    )
  }

  return null
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 询价详情组件
 *
 * Requirements:
 * - 4.1: 显示询价任务的基本信息（保全金额、状态、时间信息）
 * - 4.2: 显示所有保险公司的询价结果列表
 * - 4.4: 任务状态为 pending 时显示"执行询价"按钮
 * - 4.5: 用户点击"执行询价"时调用执行 API 并开始轮询状态
 * - 4.8: 任务失败时显示"重试"按钮
 * - 4.9: 用户点击"重试"时调用重试 API 并重新开始轮询
 *
 * @example
 * ```tsx
 * <QuoteDetail quoteId={123} />
 * ```
 */
export function QuoteDetail({ quoteId }: QuoteDetailProps) {
  const navigate = useNavigate()

  // ========== 数据查询（带轮询） ==========
  const {
    data: quote,
    isLoading,
    error,
    isFetching,
  } = useQuote(quoteId, { enablePolling: true })

  // ========== Mutations ==========
  // Requirements: 4.5 - 执行询价
  const executeQuote = useExecuteQuote()
  // Requirements: 4.9 - 重试询价
  const retryQuote = useRetryQuote()

  // ========== 事件处理 ==========

  /**
   * 返回列表
   */
  const handleBack = useCallback(() => {
    navigate('/admin/automation/preservation-quotes')
  }, [navigate])

  /**
   * 执行询价
   * Requirements: 4.5
   */
  const handleExecute = useCallback(() => {
    executeQuote.mutate(quoteId)
  }, [executeQuote, quoteId])

  /**
   * 重试询价
   * Requirements: 4.9
   */
  const handleRetry = useCallback(() => {
    retryQuote.mutate(quoteId)
  }, [retryQuote, quoteId])

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
  if (!quote) {
    return (
      <ErrorState
        error={new Error('询价任务不存在')}
        onBack={handleBack}
      />
    )
  }

  // 判断是否正在轮询
  const isPolling = shouldPoll(quote.status) && isFetching

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
            询价详情
          </h1>

          {/* 状态徽章 */}
          <QuoteStatusBadge status={quote.status} />

          {/* 轮询指示器 */}
          <PollingIndicator isPolling={isPolling} />
        </div>

        {/* 操作按钮 */}
        <div className="flex items-center gap-2">
          <ActionButtons
            quote={quote}
            onExecute={handleExecute}
            onRetry={handleRetry}
            isExecuting={executeQuote.isPending}
            isRetrying={retryQuote.isPending}
          />
        </div>
      </div>

      {/* ========== Basic Info Card ========== */}
      {/* Requirements: 4.1 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">基本信息</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {/* 保全金额 */}
            <InfoItem
              icon={<Banknote className="size-3.5" />}
              label="保全金额"
              value={
                <span className="text-primary text-base font-semibold">
                  {formatAmount(quote.preserve_amount)}
                </span>
              }
            />

            {/* 创建时间 */}
            <InfoItem
              icon={<Calendar className="size-3.5" />}
              label="创建时间"
              value={formatDateTime(quote.created_at)}
            />

            {/* 开始时间 */}
            <InfoItem
              icon={<Clock className="size-3.5" />}
              label="开始时间"
              value={formatDateTime(quote.started_at)}
            />

            {/* 完成时间 */}
            <InfoItem
              icon={<Clock className="size-3.5" />}
              label="完成时间"
              value={formatDateTime(quote.finished_at)}
            />

            {/* 成功数量 */}
            <InfoItem
              icon={<CheckCircle2 className="size-3.5 text-green-500" />}
              label="成功数量"
              value={
                <span className="text-green-600 dark:text-green-400">
                  {quote.success_count} / {quote.total_companies}
                </span>
              }
            />

            {/* 失败数量 */}
            <InfoItem
              icon={<XCircle className="size-3.5 text-red-500" />}
              label="失败数量"
              value={
                <span className="text-red-600 dark:text-red-400">
                  {quote.failed_count} / {quote.total_companies}
                </span>
              }
            />
          </div>

          {/* 错误信息（如果有） */}
          {quote.error_message && (
            <div className="bg-destructive/10 text-destructive mt-4 rounded-md p-3 text-sm">
              <strong>错误信息：</strong>
              {quote.error_message}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ========== Insurance Quotes Table ========== */}
      {/* Requirements: 4.2 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">保险报价列表</CardTitle>
        </CardHeader>
        <CardContent>
          <InsuranceQuoteTable quotes={quote.quotes} />
        </CardContent>
      </Card>
    </div>
  )
}

export default QuoteDetail
