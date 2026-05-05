import { Search } from 'lucide-react'

import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  type SimpleCaseType,
  type CaseStatus,
  type CaseListParams,
  SIMPLE_CASE_TYPE_LABELS,
  CASE_STATUS_LABELS,
} from '../types'

export interface CaseFiltersProps {
  filters: CaseListParams
  onFiltersChange: (filters: CaseListParams) => void
}

const CASE_TYPE_OPTIONS: { value: SimpleCaseType; label: string }[] = (
  Object.entries(SIMPLE_CASE_TYPE_LABELS) as [SimpleCaseType, { zh: string }][]
).map(([value, label]) => ({ value, label: label.zh }))

const CASE_STATUS_OPTIONS: { value: CaseStatus; label: string }[] = (
  Object.entries(CASE_STATUS_LABELS) as [CaseStatus, { zh: string }][]
).map(([value, label]) => ({ value, label: label.zh }))

export function CaseFilters({ filters, onFiltersChange }: CaseFiltersProps) {
  const handleCaseTypeChange = (value: string) => {
    onFiltersChange({
      ...filters,
      case_type: value === 'all' ? undefined : (value as SimpleCaseType),
    })
  }

  const handleStatusChange = (value: string) => {
    onFiltersChange({
      ...filters,
      status: value === 'all' ? undefined : value,
    })
  }

  const handleCaseNumberChange = (value: string) => {
    onFiltersChange({
      ...filters,
      case_number: value || undefined,
    })
  }

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-3">
      {/* 案号搜索 */}
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="搜索案号..."
          className="pl-8 w-full sm:w-[200px] h-9"
          value={filters.case_number ?? ''}
          onChange={(e) => handleCaseNumberChange(e.target.value)}
        />
      </div>

      {/* 案件类型筛选 */}
      <Select
        value={filters.case_type ?? 'all'}
        onValueChange={handleCaseTypeChange}
      >
        <SelectTrigger className="w-full sm:w-[140px]">
          <SelectValue placeholder="案件类型" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全部类型</SelectItem>
          {CASE_TYPE_OPTIONS.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* 案件状态筛选 */}
      <Select
        value={filters.status ?? 'all'}
        onValueChange={handleStatusChange}
      >
        <SelectTrigger className="w-full sm:w-[140px]">
          <SelectValue placeholder="案件状态" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">全部状态</SelectItem>
          {CASE_STATUS_OPTIONS.map((opt) => (
            <SelectItem key={opt.value} value={opt.value}>
              {opt.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}
