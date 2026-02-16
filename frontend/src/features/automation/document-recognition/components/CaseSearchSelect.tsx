/**
 * CaseSearchSelect Component
 *
 * 案件搜索选择组件
 * - 提供搜索输入框（带防抖）
 * - 显示搜索结果下拉列表
 * - 显示案件名称和案号
 * - 支持选择案件
 *
 * Requirements: 7.6, 7.7
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import { Search, X, Loader2, FileSearch, Check } from 'lucide-react'

import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

import { useCaseSearch } from '../hooks/use-case-search'
import type { CaseSearchResult } from '../types'

// ============================================================================
// Types
// ============================================================================

export interface CaseSearchSelectProps {
  /** 选中的案件 */
  value?: CaseSearchResult | null
  /** 选择回调 */
  onSelect: (case_: CaseSearchResult) => void
  /** 占位符文本 */
  placeholder?: string
  /** 是否禁用 */
  disabled?: boolean
  /** 自定义类名 */
  className?: string
}

// ============================================================================
// Constants
// ============================================================================

/** 最小搜索字符数提示 */
const MIN_CHARS_HINT = '请输入至少 2 个字符搜索'

// ============================================================================
// Sub-components
// ============================================================================

/**
 * 搜索结果项组件
 */
interface SearchResultItemProps {
  case_: CaseSearchResult
  isSelected: boolean
  onSelect: (case_: CaseSearchResult) => void
}

function SearchResultItem({ case_, isSelected, onSelect }: SearchResultItemProps) {
  return (
    <button
      type="button"
      className={cn(
        'flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left transition-colors',
        'hover:bg-accent focus:bg-accent focus:outline-none',
        isSelected && 'bg-accent'
      )}
      onClick={() => onSelect(case_)}
    >
      <div className="flex-1 min-w-0">
        <div className="text-foreground truncate text-sm font-medium">
          {case_.name}
        </div>
        <div className="text-muted-foreground truncate text-xs">
          {case_.case_number}
        </div>
      </div>
      {isSelected && (
        <Check className="text-primary size-4 shrink-0" />
      )}
    </button>
  )
}

/**
 * 空状态组件
 */
interface EmptyStateProps {
  query: string
}

function EmptyState({ query }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center">
      <FileSearch className="text-muted-foreground/50 mb-2 size-10" />
      <p className="text-muted-foreground text-sm">
        未找到与 "{query}" 相关的案件
      </p>
      <p className="text-muted-foreground/70 mt-1 text-xs">
        请尝试其他关键词
      </p>
    </div>
  )
}

/**
 * 加载状态组件
 */
function LoadingState() {
  return (
    <div className="flex items-center justify-center py-8">
      <Loader2 className="text-muted-foreground size-6 animate-spin" />
      <span className="text-muted-foreground ml-2 text-sm">搜索中...</span>
    </div>
  )
}

/**
 * 提示状态组件
 */
function HintState() {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center">
      <Search className="text-muted-foreground/50 mb-2 size-10" />
      <p className="text-muted-foreground text-sm">{MIN_CHARS_HINT}</p>
    </div>
  )
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 案件搜索选择组件
 *
 * 提供案件搜索和选择功能，支持：
 * - 防抖搜索（300ms）
 * - 搜索结果下拉展示
 * - 显示案件名称和案号
 * - 加载状态和空状态处理
 *
 * Requirements:
 * - 7.6: 提供案件搜索功能用于手动绑定
 * - 7.7: 显示匹配的案件列表
 *
 * @example
 * ```tsx
 * const [selectedCase, setSelectedCase] = useState<CaseSearchResult | null>(null)
 *
 * <CaseSearchSelect
 *   value={selectedCase}
 *   onSelect={setSelectedCase}
 *   placeholder="搜索案件..."
 * />
 * ```
 */
export function CaseSearchSelect({
  value,
  onSelect,
  placeholder = '搜索案件名称或案号...',
  disabled = false,
  className,
}: CaseSearchSelectProps) {
  // ========== State ==========
  const [query, setQuery] = useState('')
  const [isOpen, setIsOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  // ========== Hooks ==========
  const { data: searchResults, isLoading } = useCaseSearch(query)

  // ========== Effects ==========

  // 点击外部关闭下拉
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [])

  // ========== Handlers ==========

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const newQuery = e.target.value
      setQuery(newQuery)
      // 有输入时打开下拉
      if (newQuery.length > 0) {
        setIsOpen(true)
      }
    },
    []
  )

  const handleInputFocus = useCallback(() => {
    // 聚焦时如果有查询或已选中值，打开下拉
    if (query.length > 0 || value) {
      setIsOpen(true)
    }
  }, [query, value])

  const handleSelect = useCallback(
    (case_: CaseSearchResult) => {
      onSelect(case_)
      setQuery('')
      setIsOpen(false)
    },
    [onSelect]
  )

  const handleClear = useCallback(() => {
    setQuery('')
    setIsOpen(false)
    inputRef.current?.focus()
  }, [])

  // ========== Computed ==========

  // 判断是否显示下拉内容
  const showDropdown = isOpen && !disabled
  const hasQuery = query.trim().length > 0
  const hasMinChars = query.trim().length >= 2
  const hasResults = searchResults && searchResults.length > 0

  // ========== Render ==========

  return (
    <div ref={containerRef} className={cn('relative w-full', className)}>
      {/* 已选中的案件显示 */}
      {value && !isOpen && (
        <div
          className={cn(
            'border-input bg-background flex items-center gap-2 rounded-md border px-3 py-2',
            'dark:bg-input/30',
            disabled && 'cursor-not-allowed opacity-50'
          )}
        >
          <div className="flex-1 min-w-0">
            <div className="text-foreground truncate text-sm font-medium">
              {value.name}
            </div>
            <div className="text-muted-foreground truncate text-xs">
              {value.case_number}
            </div>
          </div>
          {!disabled && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="size-6 shrink-0 p-0"
              onClick={() => {
                setIsOpen(true)
                setTimeout(() => inputRef.current?.focus(), 0)
              }}
            >
              <Search className="size-4" />
              <span className="sr-only">重新搜索</span>
            </Button>
          )}
        </div>
      )}

      {/* 搜索输入框 */}
      {(!value || isOpen) && (
        <div className="relative">
          <Search className="text-muted-foreground pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2" />
          <Input
            ref={inputRef}
            type="text"
            value={query}
            onChange={handleInputChange}
            onFocus={handleInputFocus}
            placeholder={placeholder}
            disabled={disabled}
            className="pl-9 pr-9"
            autoComplete="off"
          />
          {/* 清除按钮 */}
          {hasQuery && !disabled && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="absolute right-1 top-1/2 size-7 -translate-y-1/2 p-0"
              onClick={handleClear}
            >
              <X className="size-4" />
              <span className="sr-only">清除</span>
            </Button>
          )}
        </div>
      )}

      {/* 下拉列表 */}
      {showDropdown && (
        <div
          className={cn(
            'bg-popover text-popover-foreground absolute z-50 mt-1 w-full rounded-md border shadow-md',
            'max-h-[300px] overflow-y-auto'
          )}
        >
          {/* 加载状态 */}
          {isLoading && <LoadingState />}

          {/* 提示状态 - 输入不足 */}
          {!isLoading && hasQuery && !hasMinChars && <HintState />}

          {/* 空状态 - 无结果 */}
          {!isLoading && hasMinChars && !hasResults && (
            <EmptyState query={query} />
          )}

          {/* 搜索结果列表 */}
          {!isLoading && hasResults && (
            <div className="p-1">
              {searchResults.map((case_) => (
                <SearchResultItem
                  key={case_.id}
                  case_={case_}
                  isSelected={value?.id === case_.id}
                  onSelect={handleSelect}
                />
              ))}
            </div>
          )}

          {/* 初始状态 - 无输入 */}
          {!isLoading && !hasQuery && !value && <HintState />}
        </div>
      )}
    </div>
  )
}

export default CaseSearchSelect
