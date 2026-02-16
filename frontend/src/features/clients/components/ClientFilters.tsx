/**
 * ClientFilters Component
 *
 * 当事人列表筛选组件
 * - 搜索框：支持按姓名、手机号、身份证号搜索
 * - 类型筛选：自然人、法人、非法人组织
 *
 * Requirements: 3.3, 3.4
 */

import { Search, X } from 'lucide-react'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { type ClientType, CLIENT_TYPE_LABELS } from '../types'

// ============================================================================
// Types
// ============================================================================

export interface ClientFiltersProps {
  /** 当前搜索关键词 */
  search: string
  /** 搜索关键词变化回调 */
  onSearchChange: (value: string) => void
  /** 当前选中的类型筛选 */
  clientType: ClientType | undefined
  /** 类型筛选变化回调 */
  onClientTypeChange: (value: ClientType | undefined) => void
}

// ============================================================================
// Constants
// ============================================================================

/** 类型筛选选项 */
const CLIENT_TYPE_OPTIONS: { value: ClientType; label: string }[] = [
  { value: 'natural', label: CLIENT_TYPE_LABELS.natural },
  { value: 'legal', label: CLIENT_TYPE_LABELS.legal },
  { value: 'non_legal_org', label: CLIENT_TYPE_LABELS.non_legal_org },
]

// ============================================================================
// Component
// ============================================================================

export function ClientFilters({
  search,
  onSearchChange,
  clientType,
  onClientTypeChange,
}: ClientFiltersProps) {
  /** 清除搜索关键词 */
  const handleClearSearch = () => {
    onSearchChange('')
  }

  /** 处理类型筛选变化 */
  const handleClientTypeChange = (value: string) => {
    if (value === 'all') {
      onClientTypeChange(undefined)
    } else {
      onClientTypeChange(value as ClientType)
    }
  }

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
      {/* 搜索框 */}
      <div className="relative flex-1 sm:max-w-xs">
        <Search className="text-muted-foreground absolute left-3 top-1/2 size-4 -translate-y-1/2" />
        <Input
          type="text"
          placeholder="搜索姓名、手机号、身份证号..."
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

      {/* 类型筛选下拉框 */}
      <Select
        value={clientType ?? 'all'}
        onValueChange={handleClientTypeChange}
      >
        <SelectTrigger className="w-full sm:w-[160px]">
          <SelectValue placeholder="全部类型" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全部类型</SelectItem>
          {CLIENT_TYPE_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
