/**
 * LawyerFilters Component
 *
 * 律师列表筛选组件
 * - 搜索框：支持按用户名、真实姓名、手机号搜索
 *
 * Requirements: 3.3
 */

import { Search, X } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'

// ============================================================================
// Types
// ============================================================================

export interface LawyerFiltersProps {
  /** 当前搜索关键词 */
  search: string
  /** 搜索关键词变化回调 */
  onSearchChange: (value: string) => void
}

// ============================================================================
// Component
// ============================================================================

export function LawyerFilters({ search, onSearchChange }: LawyerFiltersProps) {
  /** 清除搜索关键词 */
  const handleClearSearch = () => {
    onSearchChange('')
  }

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
      {/* 搜索框 */}
      <div className="relative flex-1 sm:max-w-xs">
        <Search className="text-muted-foreground absolute left-3 top-1/2 size-4 -translate-y-1/2" />
        <Input
          type="text"
          placeholder="搜索用户名、姓名、手机号..."
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          className="pl-9 pr-9"
        />
        {search && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleClearSearch}
            className="absolute right-1 top-1/2 size-7 -translate-y-1/2 p-0 hover:bg-transparent"
          >
            <X className="text-muted-foreground hover:text-foreground size-4" />
            <span className="sr-only">清除搜索</span>
          </Button>
        )}
      </div>
    </div>
  )
}
