/**
 * CaseList - 案件列表主组件
 *
 * 组合 CaseFilters + CaseTable + 搜索 + 新建按钮 + 客户端分页
 * Requirements: 2.1, 2.2, 2.5, 2.8, 10.1
 */

import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router'
import { Plus, Search, X, Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PATHS } from '@/routes/paths'
import { PageFooter } from '@/components/shared/PageFooter'

import { CaseFilters } from './CaseFilters'
import { CaseTable } from './CaseTable'
import { useCases } from '../hooks/use-cases'
import { useCaseSearch } from '../hooks/use-case-search'
import { useCaseMutations } from '../hooks/use-case-mutations'
import type { CaseListParams } from '../types'

const PAGE_SIZE = 20

// ============================================================================
// Debounce hook
// ============================================================================

function useDebounce(value: string, delay: number): string {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

// ============================================================================
// Main Component
// ============================================================================

export function CaseList() {
  const navigate = useNavigate()

  // Search state
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounce(search, 300)

  // Filter state
  const [filters, setFilters] = useState<CaseListParams>({})

  // Pagination state
  const [page, setPage] = useState(1)

  // Selection state for batch operations
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [batchLoading, setBatchLoading] = useState(false)

  // Queries
  const isSearching = debouncedSearch.length >= 1
  const casesQuery = useCases(isSearching ? undefined : filters)
  const searchQuery = useCaseSearch(debouncedSearch)
  const { updateCase } = useCaseMutations()

  const allCases = isSearching
    ? (searchQuery.data ?? [])
    : (casesQuery.data ?? [])
  const isLoading = isSearching ? searchQuery.isLoading : casesQuery.isLoading

  // Client-side pagination
  const total = allCases.length
  const paginatedCases = useMemo(
    () => allCases.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [allCases, page],
  )

  // Reset page when filters/search change
  useEffect(() => { setPage(1) }, [debouncedSearch, filters])

  // Clear selection when page changes
  useEffect(() => { setSelectedIds(new Set()) }, [page])

  // Handlers
  const handleFiltersChange = useCallback((next: CaseListParams) => {
    setFilters(next)
  }, [])

  const handleBatchAction = async (status: 'active' | 'closed') => {
    if (selectedIds.size === 0) return
    setBatchLoading(true)
    const ids = Array.from(selectedIds)
    const label = status === 'closed' ? '关闭' : '重开'
    try {
      await Promise.all(ids.map((id) => updateCase.mutateAsync({ id, data: { status } })))
      toast.success(`已${label} ${ids.length} 个案件`)
      setSelectedIds(new Set())
    } catch {
      toast.error(`批量${label}失败`)
    } finally {
      setBatchLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Top bar: search + filters + create button */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-3">
          {/* Search input */}
          <div className="relative sm:max-w-xs">
            <Search className="text-muted-foreground absolute left-3 top-1/2 size-4 -translate-y-1/2" />
            <Input
              type="text"
              placeholder="搜索案件名称..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9 pr-9"
            />
            {search && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setSearch('')}
                className="absolute right-1 top-1/2 size-7 -translate-y-1/2 p-0 hover:bg-transparent"
              >
                <X className="text-muted-foreground hover:text-foreground size-4" />
                <span className="sr-only">清除搜索</span>
              </Button>
            )}
          </div>

          {/* Filters (hidden when searching) */}
          {!isSearching && (
            <CaseFilters filters={filters} onFiltersChange={handleFiltersChange} />
          )}
        </div>

        {/* Create button */}
        <Button onClick={() => navigate(PATHS.ADMIN_CASE_NEW)} className="w-full sm:w-auto">
          <Plus className="mr-1.5 size-4" />
          新建案件
        </Button>
      </div>

      {/* Batch action bar */}
      {selectedIds.size > 0 && (
        <div className="flex items-center gap-3 rounded-md border bg-muted/50 px-4 py-2">
          <span className="text-sm text-muted-foreground">
            已选 <span className="font-medium text-foreground">{selectedIds.size}</span> 项
          </span>
          <div className="flex-1" />
          <Button
            size="sm"
            variant="outline"
            disabled={batchLoading}
            onClick={() => handleBatchAction('closed')}
          >
            {batchLoading && <Loader2 className="mr-1 size-3 animate-spin" />}
            批量关闭
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={batchLoading}
            onClick={() => handleBatchAction('active')}
          >
            {batchLoading && <Loader2 className="mr-1 size-3 animate-spin" />}
            批量重开
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setSelectedIds(new Set())}
          >
            取消选择
          </Button>
        </div>
      )}

      {/* Table */}
      <CaseTable
        cases={paginatedCases}
        isLoading={isLoading}
        selectedIds={selectedIds}
        onSelectionChange={setSelectedIds}
      />

      {/* Pagination */}
      <PageFooter
        stats={[{ label: '共', value: `${total} 条` }]}
        page={page}
        total={total}
        pageSize={PAGE_SIZE}
        onPageChange={setPage}
      />
    </div>
  )
}

export default CaseList
