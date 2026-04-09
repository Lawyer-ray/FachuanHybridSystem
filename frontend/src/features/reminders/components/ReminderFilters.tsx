/**
 * ReminderFilters Component
 * 提醒筛选组件
 *
 * 提供类型筛选、日期范围筛选和清除筛选功能
 * 支持明亮/暗夜主题
 *
 * @module features/reminders/components/ReminderFilters
 *
 * Requirements:
 * - 3.1: 用户选择提醒类型筛选
 * - 3.2: 用户选择日期范围筛选
 * - 3.3: 用户清除筛选条件
 * - 9.1: 支持明亮模式
 * - 9.2: 支持暗夜模式
 */

import { format } from 'date-fns'
import { CalendarIcon, FilterX } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'

import type { ReminderFilters as ReminderFiltersType, ReminderTypeOption } from '../types'

// ============================================================================
// Types
// ============================================================================

interface ReminderFiltersProps {
  /** 当前筛选条件 */
  filters: ReminderFiltersType
  /** 筛选条件变更回调 */
  onFiltersChange: (filters: ReminderFiltersType) => void
  /** 提醒类型选项列表 */
  reminderTypes: ReminderTypeOption[]
}

// ============================================================================
// Component
// ============================================================================

/**
 * 提醒筛选组件
 *
 * 提供以下筛选功能：
 * - 按提醒类型筛选
 * - 按日期范围筛选（起始日期、结束日期）
 * - 清除所有筛选条件
 */
export function ReminderFilters({
  filters,
  onFiltersChange,
  reminderTypes,
}: ReminderFiltersProps) {
  // 检查是否有任何筛选条件
  const hasFilters = Boolean(
    filters.reminderType || filters.dateFrom || filters.dateTo
  )

  // 处理类型筛选变更
  const handleTypeChange = (value: string) => {
    onFiltersChange({
      ...filters,
      reminderType: value === 'all' ? undefined : (value as ReminderFiltersType['reminderType']),
    })
  }

  // 处理起始日期变更
  const handleDateFromChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    onFiltersChange({
      ...filters,
      dateFrom: value ? new Date(value) : undefined,
    })
  }

  // 处理结束日期变更
  const handleDateToChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value
    onFiltersChange({
      ...filters,
      dateTo: value ? new Date(value) : undefined,
    })
  }

  // 清除所有筛选条件
  const handleClearFilters = () => {
    onFiltersChange({
      reminderType: undefined,
      dateFrom: undefined,
      dateTo: undefined,
    })
  }

  // 格式化日期为 input[type="date"] 所需的格式
  const formatDateForInput = (date: Date | undefined): string => {
    if (!date) return ''
    return format(date, 'yyyy-MM-dd')
  }

  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:flex-wrap">
      {/* 类型筛选 */}
      <div className="flex flex-col gap-1.5">
        <Label
          htmlFor="reminder-type-filter"
          className="text-sm font-medium text-foreground"
        >
          提醒类型
        </Label>
        <Select
          value={filters.reminderType || 'all'}
          onValueChange={handleTypeChange}
        >
          <SelectTrigger
            id="reminder-type-filter"
            className="w-full sm:w-[180px]"
          >
            <SelectValue placeholder="全部类型" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">全部类型</SelectItem>
            {reminderTypes.map((type) => (
              <SelectItem key={type.value} value={type.value}>
                {type.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* 起始日期 */}
      <div className="flex flex-col gap-1.5">
        <Label
          htmlFor="date-from-filter"
          className="text-sm font-medium text-foreground"
        >
          起始日期
        </Label>
        <div className="relative">
          <CalendarIcon className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />
          <Input
            id="date-from-filter"
            type="date"
            value={formatDateForInput(filters.dateFrom)}
            onChange={handleDateFromChange}
            className={cn(
              'w-full sm:w-[160px] pl-9',
              '[&::-webkit-calendar-picker-indicator]:opacity-0',
              '[&::-webkit-calendar-picker-indicator]:absolute',
              '[&::-webkit-calendar-picker-indicator]:inset-0',
              '[&::-webkit-calendar-picker-indicator]:w-full',
              '[&::-webkit-calendar-picker-indicator]:h-full',
              '[&::-webkit-calendar-picker-indicator]:cursor-pointer'
            )}
          />
        </div>
      </div>

      {/* 结束日期 */}
      <div className="flex flex-col gap-1.5">
        <Label
          htmlFor="date-to-filter"
          className="text-sm font-medium text-foreground"
        >
          结束日期
        </Label>
        <div className="relative">
          <CalendarIcon className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-muted-foreground pointer-events-none" />
          <Input
            id="date-to-filter"
            type="date"
            value={formatDateForInput(filters.dateTo)}
            onChange={handleDateToChange}
            min={formatDateForInput(filters.dateFrom)}
            className={cn(
              'w-full sm:w-[160px] pl-9',
              '[&::-webkit-calendar-picker-indicator]:opacity-0',
              '[&::-webkit-calendar-picker-indicator]:absolute',
              '[&::-webkit-calendar-picker-indicator]:inset-0',
              '[&::-webkit-calendar-picker-indicator]:w-full',
              '[&::-webkit-calendar-picker-indicator]:h-full',
              '[&::-webkit-calendar-picker-indicator]:cursor-pointer'
            )}
          />
        </div>
      </div>

      {/* 清除筛选按钮 */}
      <div className="flex items-end">
        <Button
          variant="outline"
          size="sm"
          onClick={handleClearFilters}
          disabled={!hasFilters}
          className="gap-1.5"
        >
          <FilterX className="size-4" />
          <span className="hidden sm:inline">清除筛选</span>
          <span className="sm:hidden">清除</span>
        </Button>
      </div>
    </div>
  )
}

// ============================================================================
// Default Export
// ============================================================================

export default ReminderFilters
