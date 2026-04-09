/**
 * CaseList - 案件列表主组件
 *
 * 组合 CaseFilters + CaseTable + 搜索 + 新建按钮 + 客户端分页
 * Requirements: 2.1, 2.2, 2.5, 2.8, 10.1
 */

import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router'
import { Plus, Search, X, ChevronLeft, ChevronRight } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PATHS } from '@/routes/paths'

import { CaseFilters } from './CaseFilters'
import { CaseTable } from './CaseTable'
import { useCases } from '../hooks/use-cases'
import { useCaseSearch } from '../hooks/use-case-search'
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

  // Queries
  const isSearching = debouncedSearch.length >= 1
  const casesQuery = useCases(isSearching ? undefined : filters)
  const searchQuery = useCaseSearch(debouncedSearch)

  const allCases = isSearching
    ? (searchQuery.data ?? [])
    : (casesQuery.data ?? [])
  const isLoading = isSearching ? searchQuery.isLoading : casesQuery.isLoading

  // Client-side pagination
  const total = allCases.length
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const paginatedCases = useMemo(
    () => allCases.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [allCases, page],
  )

  // Reset page when filters/search change
  useEffect(() => { setPage(1) }, [debouncedSearch, filters])

  // Handlers
  const handleFiltersChange = useCallback((next: CaseListParams) => {
    setFilters(next)
  }, [])

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

      {/* Table */}
      <CaseTable cases={paginatedCases} isLoading={isLoading} />

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <p className="text-muted-foreground text-sm">
            共 <span className="text-foreground font-medium">{total}</span> 条
          </p>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setPage(p => p - 1)} disabled={page <= 1} className="h-8 w-8 p-0">
              <ChevronLeft className="size-4" />
            </Button>
            <span className="text-sm">{page} / {totalPages}</span>
            <Button variant="outline" size="sm" onClick={() => setPage(p => p + 1)} disabled={page >= totalPages} className="h-8 w-8 p-0">
              <ChevronRight className="size-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

export default CaseList
