/**
 * ClientFilters Component
 *
 * 当事人列表筛选组件
 * - 搜索框：支持按姓名、手机号、身份证号搜索
 * - 筛选面板：类型、我方当事人
 *
 * Requirements: 3.3, 3.4
 */

import { useState } from 'react'
import { Search, X, SlidersHorizontal } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Separator } from '@/components/ui/separator'
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
  /** 当前我方当事人筛选 */
  isOurClient: boolean | undefined
  /** 我方当事人筛选变化回调 */
  onIsOurClientChange: (value: boolean | undefined) => void
}

// ============================================================================
// Component
// ============================================================================

export function ClientFilters({
  search,
  onSearchChange,
  clientType,
  onClientTypeChange,
  isOurClient,
  onIsOurClientChange,
}: ClientFiltersProps) {
  const [open, setOpen] = useState(false)

  const activeFilterCount = [clientType, isOurClient !== undefined ? isOurClient : null].filter(Boolean).length

  const clearAll = () => {
    onClientTypeChange(undefined)
    onIsOurClientChange(undefined)
  }

  return (
    <div className="flex items-center gap-3">
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
            onClick={() => onSearchChange('')}
            className="absolute right-1 top-1/2 size-7 -translate-y-1/2 p-0 hover:bg-transparent"
          >
            <X className="text-muted-foreground hover:text-foreground size-4" />
            <span className="sr-only">清除搜索</span>
          </Button>
        )}
      </div>

      {/* 筛选面板 */}
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
            {/* 当事人类型 */}
            <div className="space-y-2">
              <h4 className="text-sm font-medium">当事人类型</h4>
              <div className="flex flex-wrap gap-1.5">
                <FilterChip
                  label="全部"
                  active={!clientType}
                  onClick={() => onClientTypeChange(undefined)}
                />
                {Object.entries(CLIENT_TYPE_LABELS).map(([k, v]) => (
                  <FilterChip
                    key={k}
                    label={v}
                    active={clientType === k}
                    onClick={() => onClientTypeChange(clientType === k ? undefined : k as ClientType)}
                  />
                ))}
              </div>
            </div>

            <Separator />

            {/* 我方当事人 */}
            <div className="space-y-2">
              <h4 className="text-sm font-medium">我方当事人</h4>
              <div className="flex flex-wrap gap-1.5">
                <FilterChip
                  label="全部"
                  active={isOurClient === undefined}
                  onClick={() => onIsOurClientChange(undefined)}
                />
                <FilterChip
                  label="我方当事人"
                  active={isOurClient === true}
                  onClick={() => onIsOurClientChange(isOurClient === true ? undefined : true)}
                />
                <FilterChip
                  label="非我方当事人"
                  active={isOurClient === false}
                  onClick={() => onIsOurClientChange(isOurClient === false ? undefined : false)}
                />
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
    </div>
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
