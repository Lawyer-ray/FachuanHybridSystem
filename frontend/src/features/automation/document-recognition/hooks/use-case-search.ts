/**
 * useCaseSearch Hook
 * 案件搜索 hook（带防抖）
 *
 * 使用 TanStack Query v5 实现案件搜索，
 * 支持防抖搜索以避免过多 API 调用
 *
 * Requirements: 7.6, 7.7
 */

import { useState, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'

import { documentRecognitionApi } from '../api'
import type { CaseSearchResult } from '../types'

// ============================================================================
// Constants
// ============================================================================

/** 默认防抖延迟（毫秒） */
const DEFAULT_DEBOUNCE_MS = 300

/** 默认最小搜索字符数 */
const DEFAULT_MIN_CHARS = 2

// ============================================================================
// Types
// ============================================================================

/**
 * useCaseSearch Hook 配置选项
 */
export interface UseCaseSearchOptions {
  /** 防抖延迟（毫秒，默认 300） */
  debounceMs?: number
  /** 最小搜索字符数（默认 2） */
  minChars?: number
}

/**
 * useCaseSearch Hook 返回值
 */
export interface UseCaseSearchResult {
  /** 搜索结果数据 */
  data: CaseSearchResult[] | undefined
  /** 是否正在加载 */
  isLoading: boolean
  /** 错误信息 */
  error: Error | null
}

// ============================================================================
// Query Key Factory
// ============================================================================

/**
 * 案件搜索查询键
 *
 * @param query - 搜索关键词
 * @returns 查询键数组
 */
export const caseSearchQueryKey = (query: string) =>
  ['document-recognition', 'case-search', query] as const

// ============================================================================
// Hook: useDebounce
// ============================================================================

/**
 * 防抖 Hook
 *
 * 延迟更新值，用于减少频繁的 API 调用
 *
 * @param value - 需要防抖的值
 * @param delay - 延迟时间（毫秒）
 * @returns 防抖后的值
 */
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    // 设置定时器，在延迟后更新值
    const timer = setTimeout(() => {
      setDebouncedValue(value)
    }, delay)

    // 清理函数：如果值在延迟期间改变，取消之前的定时器
    return () => {
      clearTimeout(timer)
    }
  }, [value, delay])

  return debouncedValue
}

// ============================================================================
// Hook: useCaseSearch
// ============================================================================

/**
 * 案件搜索 Hook（带防抖）
 *
 * 实现防抖搜索功能，避免用户输入时频繁调用 API。
 * 只有当搜索词长度达到最小字符数时才会发起请求。
 *
 * @param query - 搜索关键词
 * @param options - 配置选项
 * @returns 搜索结果，包含 data、isLoading、error
 *
 * @example
 * ```tsx
 * // 基础用法
 * const [searchQuery, setSearchQuery] = useState('')
 * const { data: cases, isLoading, error } = useCaseSearch(searchQuery)
 *
 * // 自定义防抖延迟
 * const { data: cases } = useCaseSearch(searchQuery, { debounceMs: 500 })
 *
 * // 自定义最小字符数
 * const { data: cases } = useCaseSearch(searchQuery, { minChars: 3 })
 *
 * // 在案件搜索选择组件中使用
 * function CaseSearchSelect({ onSelect }: { onSelect: (case: CaseSearchResult) => void }) {
 *   const [query, setQuery] = useState('')
 *   const { data: cases, isLoading } = useCaseSearch(query)
 *
 *   return (
 *     <div>
 *       <Input
 *         value={query}
 *         onChange={(e) => setQuery(e.target.value)}
 *         placeholder="搜索案件..."
 *       />
 *       {isLoading && <Spinner />}
 *       {cases?.map((c) => (
 *         <div key={c.id} onClick={() => onSelect(c)}>
 *           {c.name} - {c.case_number}
 *         </div>
 *       ))}
 *     </div>
 *   )
 * }
 * ```
 *
 * Requirements: 7.6 (案件搜索功能), 7.7 (显示匹配的案件列表)
 */
export function useCaseSearch(
  query: string,
  options?: UseCaseSearchOptions
): UseCaseSearchResult {
  const {
    debounceMs = DEFAULT_DEBOUNCE_MS,
    minChars = DEFAULT_MIN_CHARS,
  } = options ?? {}

  // 对搜索词进行防抖处理
  const debouncedQuery = useDebounce(query.trim(), debounceMs)

  // 判断是否应该启用查询
  const shouldSearch = debouncedQuery.length >= minChars

  const {
    data,
    isLoading: queryIsLoading,
    error,
  } = useQuery<CaseSearchResult[], Error>({
    queryKey: caseSearchQueryKey(debouncedQuery),
    queryFn: () => documentRecognitionApi.searchCases(debouncedQuery),
    // 只有当搜索词达到最小长度时才启用查询
    enabled: shouldSearch,
    // 搜索结果缓存 1 分钟
    staleTime: 60 * 1000,
    // 搜索结果保留 5 分钟
    gcTime: 5 * 60 * 1000,
    // 搜索失败不自动重试
    retry: false,
    // 窗口聚焦时不自动重新获取
    refetchOnWindowFocus: false,
  })

  // 计算实际的 loading 状态
  // 当用户正在输入但还未达到防抖延迟时，也应该显示 loading
  const isDebouncing = query.trim() !== debouncedQuery && query.trim().length >= minChars
  const isLoading = shouldSearch ? (queryIsLoading || isDebouncing) : false

  return {
    data: shouldSearch ? data : undefined,
    isLoading,
    error: shouldSearch ? error : null,
  }
}

export default useCaseSearch
