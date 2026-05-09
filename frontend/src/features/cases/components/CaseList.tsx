/**
 * CaseList - 案件列表主组件
 *
 * 组合 CaseFilters + CaseTable + 搜索 + 新建按钮 + 客户端分页
 * Requirements: 2.1, 2.2, 2.5, 2.8, 10.1
 */

import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router'
import { Plus, Search, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PATHS } from '@/routes/paths'
import { PageFooter } from '@/components/shared/PageFooter'

import { useDebounce } from '@/hooks/use-debounce'
import { CaseFilters } from './CaseFilters'
import { CaseTable } from './CaseTable'
import { useCases } from '../hooks/use-cases'
import { useCaseSearch } from '../hooks/use-case-search'
import type { CaseListParams } from '../types'

const PAGE_SIZE = 20

// ============================================================================
// Main Component
// ============================================================================

export function CaseList() {
  const navigate = useNavigate()

  // Search state
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounce(search, 300)

  // Filter state
  const [filters, setFilters] = useState<CaseListParams>({ status: 'active' })

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
      <CaseTable
        cases={paginatedCases}
        isLoading={isLoading}
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
