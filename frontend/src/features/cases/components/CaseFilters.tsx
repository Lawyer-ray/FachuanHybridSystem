import { useState } from 'react'
import { SlidersHorizontal } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Separator } from '@/components/ui/separator'
import {
  type SimpleCaseType,
  type CaseListParams,
  SIMPLE_CASE_TYPE_LABELS,
  CASE_STATUS_LABELS,
} from '../types'

export interface CaseFiltersProps {
  filters: CaseListParams
  onFiltersChange: (filters: CaseListParams) => void
}

export function CaseFilters({ filters, onFiltersChange }: CaseFiltersProps) {
  const [open, setOpen] = useState(false)

  const activeFilterCount = [filters.case_type, filters.status].filter(Boolean).length

  const clearAll = () => {
    onFiltersChange({ status: 'active' })
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" className="gap-2">
          <SlidersHorizontal className="size-4" />
          筛选
          {activeFilterCount > 0 && (
            <Badge variant="secondary" className="ml-1 size-5 justify-center rounded-full p-0 text-xs">
              {activeFilterCount}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[280px] p-4" align="start">
        <div className="space-y-4">
          {/* 案件类型 */}
          <div className="space-y-2">
            <h4 className="text-sm font-medium">案件类型</h4>
            <div className="flex flex-wrap gap-1.5">
              <FilterChip
                label="全部"
                active={!filters.case_type}
                onClick={() => onFiltersChange({ ...filters, case_type: undefined })}
              />
              {Object.entries(SIMPLE_CASE_TYPE_LABELS).map(([k, v]) => (
                <FilterChip
                  key={k}
                  label={v.zh}
                  active={filters.case_type === k}
                  onClick={() => onFiltersChange({ ...filters, case_type: filters.case_type === k ? undefined : k as SimpleCaseType })}
                />
              ))}
            </div>
          </div>

          <Separator />

          {/* 状态 */}
          <div className="space-y-2">
            <h4 className="text-sm font-medium">状态</h4>
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(CASE_STATUS_LABELS).map(([k, v]) => (
                <FilterChip
                  key={k}
                  label={v.zh}
                  active={filters.status === k}
                  onClick={() => onFiltersChange({ ...filters, status: filters.status === k ? undefined : k })}
                />
              ))}
            </div>
          </div>

          {activeFilterCount > 0 && (
            <>
              <Separator />
              <Button variant="ghost" size="sm" className="w-full" onClick={clearAll}>
                清除所有筛选
              </Button>
            </>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}

function FilterChip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
        active
          ? 'bg-primary text-primary-foreground'
          : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
      }`}
    >
      {label}
    </button>
  )
}
