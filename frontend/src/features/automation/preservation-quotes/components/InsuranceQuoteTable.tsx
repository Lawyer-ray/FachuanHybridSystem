/**
 * InsuranceQuoteTable - 保险报价表格组件
 * @module features/automation/preservation-quotes/components/InsuranceQuoteTable
 *
 * 显示保险公司询价结果列表
 * - 显示公司名称、保费、费率范围、状态
 * - 支持响应式布局（移动端/平板/桌面）
 * - 支持明暗主题
 * - 错误信息可折叠展开
 * - 按保费排序，失败的放最后
 *
 * Requirements: 4.2, 4.3, 8.2, 8.3, 8.4
 */

import { useState, useMemo } from 'react'
import { CheckCircle2, XCircle, AlertCircle, ChevronDown, ChevronUp } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { cn } from '@/lib/utils'

import type { InsuranceQuote, InsuranceQuoteStatus } from '../types'

// ============================================================================
// Types
// ============================================================================

export interface InsuranceQuoteTableProps {
  /** 保险报价列表 */
  quotes: InsuranceQuote[]
  /** 自定义类名 */
  className?: string
}

// ============================================================================
// Constants
// ============================================================================

/**
 * 状态标签映射
 */
const STATUS_LABELS: Record<InsuranceQuoteStatus, string> = {
  success: '成功',
  failed: '失败',
}

/**
 * 状态样式映射（支持明暗主题）
 */
const STATUS_STYLES: Record<
  InsuranceQuoteStatus,
  { bg: string; text: string; border: string }
> = {
  success: {
    bg: 'bg-green-100 dark:bg-green-900/30',
    text: 'text-green-700 dark:text-green-400',
    border: 'border-green-200 dark:border-green-800',
  },
  failed: {
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-700 dark:text-red-400',
    border: 'border-red-200 dark:border-red-800',
  },
}

// ============================================================================
// Utility Functions
// ============================================================================

/**
 * 格式化保费金额
 * @param premium - 保费金额字符串
 * @returns 格式化后的金额或占位符
 */
function formatPremium(premium: string | null): string {
  if (premium === null || premium === '') return '-'
  const num = parseFloat(premium)
  if (isNaN(num)) return '-'
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(num)
}

/**
 * 格式化费率为百分比
 * @param rate - 费率字符串（小数形式，如 "0.005"）
 * @returns 格式化后的百分比字符串
 */
function formatRate(rate: string | null): string {
  if (rate === null || rate === '') return '-'
  const num = parseFloat(rate)
  if (isNaN(num)) return '-'
  // 将小数转换为百分比，保留 2-4 位小数
  return `${(num * 100).toFixed(2)}%`
}

/**
 * 格式化费率范围
 * @param minRate - 最低费率
 * @param maxRate - 最高费率
 * @returns 格式化后的费率范围字符串
 */
function formatRateRange(
  minRate: string | null,
  maxRate: string | null
): string {
  const min = formatRate(minRate)
  const max = formatRate(maxRate)

  if (min === '-' && max === '-') return '-'
  if (min === '-') return `≤ ${max}`
  if (max === '-') return `≥ ${min}`
  if (min === max) return min
  return `${min} - ${max}`
}

// ============================================================================
// Sub-components
// ============================================================================

/**
 * 保险报价状态徽章
 */
interface QuoteStatusBadgeProps {
  status: InsuranceQuoteStatus
  errorMessage?: string | null
}

function InsuranceQuoteStatusBadge({
  status,
  errorMessage,
}: QuoteStatusBadgeProps) {
  const [expanded, setExpanded] = useState(false)
  const styles = STATUS_STYLES[status]
  const label = STATUS_LABELS[status]
  const Icon = status === 'success' ? CheckCircle2 : XCircle

  return (
    <div className="flex flex-col gap-1">
      <Badge
        variant="outline"
        className={cn(
          'inline-flex items-center gap-1.5 border font-medium',
          styles.bg,
          styles.text,
          styles.border
        )}
      >
        <Icon className="size-3" />
        {label}
      </Badge>
      {/* 失败时显示可折叠的错误信息 */}
      {status === 'failed' && errorMessage && (
        <div className="flex flex-col gap-1">
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-xs transition-colors"
          >
            {expanded ? (
              <>
                <ChevronUp className="size-3" />
                收起
              </>
            ) : (
              <>
                <ChevronDown className="size-3" />
                查看详情
              </>
            )}
          </button>
          {expanded && (
            <span className="text-muted-foreground max-w-[300px] break-all text-xs">
              {errorMessage}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * 空状态组件
 */
function EmptyState() {
  return (
    <TableRow>
      <TableCell colSpan={4} className="h-32">
        <div className="flex flex-col items-center justify-center gap-2">
          <div className="bg-muted flex size-10 items-center justify-center rounded-full">
            <AlertCircle className="text-muted-foreground size-5" />
          </div>
          <p className="text-muted-foreground text-sm">暂无保险报价数据</p>
        </div>
      </TableCell>
    </TableRow>
  )
}

/**
 * 移动端卡片视图（< 768px）
 * Requirements: 8.2
 */
interface MobileCardProps {
  quote: InsuranceQuote
}

function MobileCard({ quote }: MobileCardProps) {
  return (
    <div className="border-border bg-card rounded-lg border p-4">
      {/* 公司名称和状态 */}
      <div className="mb-3 flex items-start justify-between gap-2">
        <h4 className="text-foreground text-sm font-medium">
          {quote.company_name}
        </h4>
        <InsuranceQuoteStatusBadge
          status={quote.status}
          errorMessage={quote.error_message}
        />
      </div>

      {/* 详细信息 */}
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <span className="text-muted-foreground text-xs">保费</span>
          <p
            className={cn(
              'font-medium',
              quote.status === 'success'
                ? 'text-foreground'
                : 'text-muted-foreground'
            )}
          >
            {formatPremium(quote.premium)}
          </p>
        </div>
        <div>
          <span className="text-muted-foreground text-xs">费率范围</span>
          <p
            className={cn(
              'font-medium',
              quote.status === 'success'
                ? 'text-foreground'
                : 'text-muted-foreground'
            )}
          >
            {formatRateRange(quote.min_rate, quote.max_rate)}
          </p>
        </div>
      </div>
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 保险报价表格组件
 *
 * Requirements:
 * - 4.2: 显示所有保险公司的询价结果列表
 * - 4.3: 为每个询价结果显示公司名称、保费、费率范围、状态
 * - 8.2: 在移动端（< 768px）使用单列布局
 * - 8.3: 在平板端（768px - 1024px）使用适中的间距和字体
 * - 8.4: 在桌面端（> 1024px）使用多列布局和更大的信息密度
 *
 * @example
 * ```tsx
 * <InsuranceQuoteTable quotes={preservationQuote.quotes} />
 * ```
 */
export function InsuranceQuoteTable({
  quotes,
  className,
}: InsuranceQuoteTableProps) {
  // 排序：成功的按保费升序，失败的放最后
  const sortedQuotes = useMemo(() => {
    if (!quotes || quotes.length === 0) return []

    return [...quotes].sort((a, b) => {
      // 失败的放最后
      if (a.status === 'failed' && b.status !== 'failed') return 1
      if (a.status !== 'failed' && b.status === 'failed') return -1

      // 都失败或都成功时，按保费升序
      const premiumA = a.premium ? parseFloat(a.premium) : Infinity
      const premiumB = b.premium ? parseFloat(b.premium) : Infinity
      return premiumA - premiumB
    })
  }, [quotes])

  // 空数据处理
  if (!quotes || quotes.length === 0) {
    return (
      <div className={cn('rounded-md border', className)}>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>保险公司</TableHead>
              <TableHead>保费</TableHead>
              <TableHead>费率范围</TableHead>
              <TableHead>状态</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <EmptyState />
          </TableBody>
        </Table>
      </div>
    )
  }

  return (
    <div className={className}>
      {/* 移动端卡片视图 - Requirements: 8.2 */}
      <div className="flex flex-col gap-3 md:hidden">
        {sortedQuotes.map((quote) => (
          <MobileCard key={quote.id} quote={quote} />
        ))}
      </div>

      {/* 平板/桌面端表格视图 - Requirements: 8.3, 8.4 */}
      <div className="hidden overflow-x-auto rounded-md border md:block">
        <Table>
          <TableHeader>
            <TableRow>
              {/*
                Requirements: 4.3
                表格列：保险公司、保费、费率范围、状态
              */}
              <TableHead className="w-[180px] text-sm lg:w-[220px] lg:text-base">
                保险公司
              </TableHead>
              <TableHead className="w-[120px] text-sm lg:w-[150px] lg:text-base">
                保费
              </TableHead>
              <TableHead className="w-[140px] text-sm lg:w-[160px] lg:text-base">
                费率范围
              </TableHead>
              <TableHead className="w-[120px] text-sm lg:w-[150px] lg:text-base">
                状态
              </TableHead>
            </TableRow>
          </TableHeader>

          <TableBody>
            {sortedQuotes.map((quote) => (
              <TableRow key={quote.id}>
                {/* 公司名称 */}
                <TableCell className="text-sm font-medium lg:text-base">
                  {quote.company_name}
                </TableCell>

                {/* 保费 - 成功时显示金额，失败时显示占位符 */}
                <TableCell
                  className={cn(
                    'text-sm lg:text-base',
                    quote.status === 'success'
                      ? 'text-foreground font-medium'
                      : 'text-muted-foreground'
                  )}
                >
                  {formatPremium(quote.premium)}
                </TableCell>

                {/* 费率范围 */}
                <TableCell
                  className={cn(
                    'text-sm lg:text-base',
                    quote.status === 'success'
                      ? 'text-foreground'
                      : 'text-muted-foreground'
                  )}
                >
                  {formatRateRange(quote.min_rate, quote.max_rate)}
                </TableCell>

                {/* 状态 */}
                <TableCell>
                  <InsuranceQuoteStatusBadge
                    status={quote.status}
                    errorMessage={quote.error_message}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

export default InsuranceQuoteTable
