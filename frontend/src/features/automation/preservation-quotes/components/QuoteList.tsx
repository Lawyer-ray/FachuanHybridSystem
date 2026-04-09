/**
 * QuoteList Component
 *
 * 财产保全询价列表组件
 * - 分页表格展示询价任务
 * - 状态筛选
 * - 骨架屏加载状态
 * - 空状态提示
 * - 点击行导航到详情
 *
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
 */

import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router'
import { Plus, ChevronLeft, ChevronRight, FileSearch } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'

import { useQuotes } from '../hooks/use-quotes'
import { QuoteStatusBadge } from './QuoteStatusBadge'
import type { QuoteStatus, PreservationQuote } from '../types'

// ============================================================================
// Constants
// ============================================================================

/** 默认每页显示条数 */
const DEFAULT_PAGE_SIZE = 10

/** 状态筛选选项 */
const STATUS_OPTIONS: { value: QuoteStatus | 'all'; label: string }[] = [
  { value: 'all', label: '全部状态' },
  { value: 'pending', label: '待执行' },
  { value: 'running', label: '执行中' },
  { value: 'success', label: '成功' },
  { value: 'partial_success', label: '部分成功' },
  { value: 'failed', label: '失败' },
]

// ============================================================================
// Types
// ============================================================================

export interface QuoteListProps {
  /** 创建询价回调 */
  onCreateClick?: () => void
}

// ============================================================================
// Sub-components
// ============================================================================

/**
 * 表格骨架屏 - 加载状态
 * Requirements: 2.3
 */
function TableSkeleton() {
  return (
    <>
      {Array.from({ length: 5 }).map((_, index) => (
        <TableRow key={index}>
          <TableCell>
            <Skeleton className="h-4 w-24" />
          </TableCell>
          <TableCell>
            <Skeleton className="h-5 w-16" />
          </TableCell>
          <TableCell>
            <Skeleton className="h-4 w-16" />
          </TableCell>
          <TableCell>
            <Skeleton className="h-4 w-28" />
          </TableCell>
        </TableRow>
      ))}
    </>
  )
}

/**
 * 空状态组件
 * Requirements: 2.4
 */
interface EmptyStateProps {
  onCreateClick?: () => void
}

function EmptyState({ onCreateClick }: EmptyStateProps) {
  return (
    <TableRow>
      <TableCell colSpan={4} className="h-48">
        <div className="flex flex-col items-center justify-center gap-3">
          <div className="bg-muted flex size-12 items-center justify-center rounded-full">
            <FileSearch className="text-muted-foreground size-6" />
          </div>
          <div className="text-center">
            <p className="text-muted-foreground text-sm font-medium">
              暂无询价任务
            </p>
            <p className="text-muted-foreground/70 mt-1 text-xs">
              点击「创建询价」按钮开始第一个询价任务
            </p>
          </div>
          {onCreateClick && (
            <Button onClick={onCreateClick} size="sm" className="mt-2">
              <Plus className="mr-2 size-4" />
              创建询价
            </Button>
          )}
        </div>
      </TableCell>
    </TableRow>
  )
}

/**
 * 分页控件组件
 */
interface PaginationProps {
  /** 当前页码（从 1 开始） */
  page: number
  /** 总页数 */
  totalPages: number
  /** 总条数 */
  total: number
  /** 每页条数 */
  pageSize: number
  /** 页码变化回调 */
  onPageChange: (page: number) => void
  /** 是否正在加载 */
  isLoading?: boolean
}

function Pagination({
  page,
  totalPages,
  total,
  pageSize,
  onPageChange,
  isLoading = false,
}: PaginationProps) {
  const startItem = total === 0 ? 0 : (page - 1) * pageSize + 1
  const endItem = Math.min(page * pageSize, total)

  const canGoPrevious = page > 1
  const canGoNext = page < totalPages

  return (
    <div className="flex flex-col items-center justify-between gap-3 sm:flex-row">
      {/* 分页信息 */}
      <p className="text-muted-foreground text-sm">
        {total === 0 ? (
          '暂无数据'
        ) : (
          <>
            显示第 <span className="text-foreground font-medium">{startItem}</span> -{' '}
            <span className="text-foreground font-medium">{endItem}</span> 条，共{' '}
            <span className="text-foreground font-medium">{total}</span> 条
          </>
        )}
      </p>

      {/* 分页按钮 */}
      {totalPages > 1 && (
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(page - 1)}
            disabled={!canGoPrevious || isLoading}
            className="h-8 w-8 p-0"
          >
            <ChevronLeft className="size-4" />
            <span className="sr-only">上一页</span>
          </Button>

          {/* 页码显示 */}
          <div className="flex items-center gap-1">
            {generatePageNumbers(page, totalPages).map((pageNum, index) =>
              pageNum === '...' ? (
                <span
                  key={`ellipsis-${index}`}
                  className="text-muted-foreground px-2 text-sm"
                >
                  ...
                </span>
              ) : (
                <Button
                  key={pageNum}
                  variant={pageNum === page ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => onPageChange(pageNum as number)}
                  disabled={isLoading}
                  className="h-8 w-8 p-0"
                >
                  {pageNum}
                </Button>
              )
            )}
          </div>

          <Button
            variant="outline"
            size="sm"
            onClick={() => onPageChange(page + 1)}
            disabled={!canGoNext || isLoading}
            className="h-8 w-8 p-0"
          >
            <ChevronRight className="size-4" />
            <span className="sr-only">下一页</span>
          </Button>
        </div>
      )}
    </div>
  )
}

/**
 * 生成页码数组（带省略号）
 */
function generatePageNumbers(
  currentPage: number,
  totalPages: number
): (number | '...')[] {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1)
  }

  const pages: (number | '...')[] = []

  // 始终显示第一页
  pages.push(1)

  if (currentPage <= 3) {
    pages.push(2, 3, 4, '...', totalPages)
  } else if (currentPage >= totalPages - 2) {
    pages.push('...', totalPages - 3, totalPages - 2, totalPages - 1, totalPages)
  } else {
    pages.push(
      '...',
      currentPage - 1,
      currentPage,
      currentPage + 1,
      '...',
      totalPages
    )
  }

  return pages
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
    })
  } catch {
    return '-'
  }
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 询价列表组件
 *
 * Requirements:
 * - 2.1: 显示分页的询价任务列表
 * - 2.2: 显示保全金额、状态、成功/失败数量、创建时间
 * - 2.3: 数据加载中显示骨架屏加载状态
 * - 2.4: 列表为空时显示空状态提示和创建按钮
 * - 2.5: 支持按状态筛选询价任务
 * - 2.6: 点击任务行导航到该任务的详情页
 */
export function QuoteList({ onCreateClick }: QuoteListProps) {
  const navigate = useNavigate()

  // ========== 状态管理 ==========
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<QuoteStatus | 'all'>('all')

  // ========== 数据查询 ==========
  const { data, isLoading, isFetching } = useQuotes({
    page,
    page_size: DEFAULT_PAGE_SIZE,
    status: statusFilter === 'all' ? undefined : statusFilter,
  })

  // ========== 事件处理 ==========

  /**
   * 处理状态筛选变化
   * Requirements: 2.5
   */
  const handleStatusChange = useCallback((value: string) => {
    setStatusFilter(value as QuoteStatus | 'all')
    setPage(1) // 筛选时重置到第一页
  }, [])

  /**
   * 处理页码变化
   */
  const handlePageChange = useCallback((newPage: number) => {
    setPage(newPage)
  }, [])

  /**
   * 处理行点击 - 导航到详情页
   * Requirements: 2.6
   */
  const handleRowClick = useCallback(
    (quote: PreservationQuote) => {
      navigate(`/admin/automation/preservation-quotes/${quote.id}`)
    },
    [navigate]
  )

  // ========== 渲染 ==========
  const quotes = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.ceil(total / DEFAULT_PAGE_SIZE)

  return (
    <div className="flex flex-col gap-4">
      {/* 顶部操作栏：筛选 + 创建按钮 */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        {/* 状态筛选 - Requirements: 2.5 */}
        <Select value={statusFilter} onValueChange={handleStatusChange}>
          <SelectTrigger className="w-full sm:w-[180px]">
            <SelectValue placeholder="选择状态" />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* 创建按钮 */}
        {onCreateClick && (
          <Button onClick={onCreateClick} className="w-full sm:w-auto">
            <Plus className="mr-2 size-4" />
            创建询价
          </Button>
        )}
      </div>

      {/* 表格 - Requirements: 2.1, 2.2 */}
      <div className="overflow-x-auto rounded-md border">
        <Table className="min-w-[500px]">
          <TableHeader>
            <TableRow>
              <TableHead className="w-[140px] text-xs sm:w-[160px] sm:text-sm">
                保全金额
              </TableHead>
              <TableHead className="w-[100px] text-xs sm:w-[120px] sm:text-sm">
                状态
              </TableHead>
              <TableHead className="w-[100px] text-xs sm:w-[120px] sm:text-sm">
                成功/失败
              </TableHead>
              <TableHead className="w-[140px] text-xs sm:w-[160px] sm:text-sm">
                创建时间
              </TableHead>
            </TableRow>
          </TableHeader>

          <TableBody>
            {isLoading ? (
              // 骨架屏加载状态 - Requirements: 2.3
              <TableSkeleton />
            ) : quotes.length === 0 ? (
              // 空状态 - Requirements: 2.4
              <EmptyState onCreateClick={onCreateClick} />
            ) : (
              // 数据列表 - Requirements: 2.2, 2.6
              quotes.map((quote) => (
                <TableRow
                  key={quote.id}
                  onClick={() => handleRowClick(quote)}
                  className="h-11 cursor-pointer sm:h-auto"
                >
                  <TableCell className="text-xs font-medium sm:text-sm">
                    {formatAmount(quote.preserve_amount)}
                  </TableCell>
                  <TableCell>
                    <QuoteStatusBadge status={quote.status} />
                  </TableCell>
                  <TableCell className="text-xs sm:text-sm">
                    <span className="text-green-600 dark:text-green-400">
                      {quote.success_count}
                    </span>
                    <span className="text-muted-foreground mx-1">/</span>
                    <span className="text-red-600 dark:text-red-400">
                      {quote.failed_count}
                    </span>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs sm:text-sm">
                    {formatDateTime(quote.created_at)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* 分页控件 */}
      <Pagination
        page={page}
        totalPages={totalPages}
        total={total}
        pageSize={DEFAULT_PAGE_SIZE}
        onPageChange={handlePageChange}
        isLoading={isFetching}
      />
    </div>
  )
}

export default QuoteList
