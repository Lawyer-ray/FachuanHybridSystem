/**
 * ClientList Component
 *
 * 当事人列表组件
 * - 组合 ClientFilters 和 ClientTable
 * - 实现分页控件
 * - 实现新建按钮
 *
 * Requirements: 3.5, 3.6
 */

import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router'
import { Plus, ChevronLeft, ChevronRight } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { PATHS } from '@/routes/paths'

import { ClientFilters } from './ClientFilters'
import { ClientTable } from './ClientTable'
import { useClients } from '../hooks/use-clients'
import type { ClientType } from '../types'

// ============================================================================
// Constants
// ============================================================================

/** 默认每页显示条数 - Requirements: 3.5 */
const DEFAULT_PAGE_SIZE = 20

// ============================================================================
// Types
// ============================================================================

export interface ClientListProps {
  // 无需 props，内部管理状态
}

// ============================================================================
// Sub-components
// ============================================================================

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

/**
 * 分页控件组件
 * Requirements: 3.5
 */
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
 * 例如：[1, 2, 3, '...', 10] 或 [1, '...', 5, 6, 7, '...', 10]
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
    // 当前页靠近开头
    pages.push(2, 3, 4, '...', totalPages)
  } else if (currentPage >= totalPages - 2) {
    // 当前页靠近结尾
    pages.push('...', totalPages - 3, totalPages - 2, totalPages - 1, totalPages)
  } else {
    // 当前页在中间
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
// Main Component
// ============================================================================

/**
 * 当事人列表组件
 *
 * Requirements:
 * - 3.5: 支持分页，每页默认显示 20 条
 * - 3.6: 点击「新建当事人」按钮导航到新建页面
 */
export function ClientList(_props: ClientListProps) {
  const navigate = useNavigate()

  // ========== 状态管理 ==========
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [clientType, setClientType] = useState<ClientType | undefined>(undefined)

  // ========== 数据查询 ==========
  const { data, isLoading, isFetching } = useClients({
    page,
    pageSize: DEFAULT_PAGE_SIZE,
    search: search || undefined,
    clientType,
  })

  // ========== 事件处理 ==========

  /**
   * 处理搜索变化
   * 搜索时重置到第一页
   */
  const handleSearchChange = useCallback((value: string) => {
    setSearch(value)
    setPage(1)
  }, [])

  /**
   * 处理类型筛选变化
   * 筛选时重置到第一页
   */
  const handleClientTypeChange = useCallback((value: ClientType | undefined) => {
    setClientType(value)
    setPage(1)
  }, [])

  /**
   * 处理页码变化
   */
  const handlePageChange = useCallback((newPage: number) => {
    setPage(newPage)
  }, [])

  /**
   * 处理新建按钮点击
   * Requirements: 3.6
   */
  const handleCreateClick = useCallback(() => {
    navigate(PATHS.ADMIN_CLIENT_NEW)
  }, [navigate])

  // ========== 渲染 ==========
  const clients = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = data?.total_pages ?? 1

  return (
    <div className="flex flex-col gap-4">
      {/* 顶部操作栏：筛选 + 新建按钮 */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <ClientFilters
          search={search}
          onSearchChange={handleSearchChange}
          clientType={clientType}
          onClientTypeChange={handleClientTypeChange}
        />

        {/* 新建按钮 - Requirements: 3.6 */}
        <Button onClick={handleCreateClick} className="w-full sm:w-auto">
          <Plus className="mr-2 size-4" />
          新建当事人
        </Button>
      </div>

      {/* 表格 */}
      <ClientTable clients={clients} isLoading={isLoading} />

      {/* 分页控件 - Requirements: 3.5 */}
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

export default ClientList
