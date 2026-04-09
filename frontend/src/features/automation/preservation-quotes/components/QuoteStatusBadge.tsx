/**
 * QuoteStatusBadge - 询价任务状态徽章组件
 * @module features/automation/preservation-quotes/components/QuoteStatusBadge
 *
 * 显示询价任务的状态，支持所有状态类型和明暗主题
 * Requirements: 2.2, 8.1
 */

import { Loader2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

import type { QuoteStatus } from '../types'

/**
 * 状态标签映射（中文）
 */
const STATUS_LABELS: Record<QuoteStatus, string> = {
  pending: '待执行',
  running: '执行中',
  success: '成功',
  partial_success: '部分成功',
  failed: '失败',
}

/**
 * 状态样式映射
 * 支持明暗主题
 */
const STATUS_STYLES: Record<
  QuoteStatus,
  { bg: string; text: string; border: string }
> = {
  pending: {
    bg: 'bg-gray-100 dark:bg-muted',
    text: 'text-gray-700 dark:text-muted-foreground',
    border: 'border-gray-200 dark:border-border',
  },
  running: {
    bg: 'bg-blue-100 dark:bg-blue-900/30',
    text: 'text-blue-700 dark:text-blue-400',
    border: 'border-blue-200 dark:border-blue-800',
  },
  success: {
    bg: 'bg-green-100 dark:bg-green-900/30',
    text: 'text-green-700 dark:text-green-400',
    border: 'border-green-200 dark:border-green-800',
  },
  partial_success: {
    bg: 'bg-amber-100 dark:bg-amber-900/30',
    text: 'text-amber-700 dark:text-amber-400',
    border: 'border-amber-200 dark:border-amber-800',
  },
  failed: {
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-700 dark:text-red-400',
    border: 'border-red-200 dark:border-red-800',
  },
}

export interface QuoteStatusBadgeProps {
  /** 询价任务状态 */
  status: QuoteStatus
  /** 是否显示状态指示点 */
  showDot?: boolean
  /** 自定义类名 */
  className?: string
}

/**
 * 询价任务状态徽章组件
 *
 * @example
 * ```tsx
 * <QuoteStatusBadge status="pending" />
 * <QuoteStatusBadge status="running" showDot />
 * <QuoteStatusBadge status="success" />
 * ```
 */
export function QuoteStatusBadge({
  status,
  showDot = true,
  className,
}: QuoteStatusBadgeProps) {
  const styles = STATUS_STYLES[status]
  const label = STATUS_LABELS[status]
  const isRunning = status === 'running'

  return (
    <Badge
      variant="outline"
      className={cn(
        'inline-flex items-center gap-1.5 border font-medium',
        styles.bg,
        styles.text,
        styles.border,
        className
      )}
    >
      {showDot && (
        <>
          {isRunning ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <span
              className={cn(
                'h-1.5 w-1.5 rounded-full',
                status === 'pending' && 'bg-gray-500 dark:bg-gray-400',
                status === 'success' && 'bg-green-500 dark:bg-green-400',
                status === 'partial_success' && 'bg-amber-500 dark:bg-amber-400',
                status === 'failed' && 'bg-red-500 dark:bg-red-400'
              )}
            />
          )}
        </>
      )}
      {label}
    </Badge>
  )
}
