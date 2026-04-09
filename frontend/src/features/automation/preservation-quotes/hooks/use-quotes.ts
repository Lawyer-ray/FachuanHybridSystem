/**
 * useQuotes Hook
 * 财产保全询价列表查询 hook
 *
 * 使用 TanStack Query v5 实现询价列表查询（带分页和筛选）
 *
 * Requirements: 2.1, 2.5
 */

import { useQuery } from '@tanstack/react-query'

import { preservationQuoteApi } from '../api'
import type { PaginatedResponse, PreservationQuote, QuoteListParams } from '../types'

// ============================================================================
// Query Keys
// ============================================================================

/**
 * 询价列表查询 Query Key
 *
 * @param params - 查询参数（分页、状态筛选）
 * @returns Query key 数组
 */
export const quotesQueryKey = (params?: QuoteListParams) =>
  [
    'preservation-quotes',
    {
      page: params?.page ?? 1,
      page_size: params?.page_size ?? 10,
      status: params?.status ?? null,
    },
  ] as const

/**
 * 单个询价查询 Query Key
 *
 * @param id - 询价任务 ID
 * @returns Query key 数组
 */
export const quoteQueryKey = (id: number) => ['preservation-quote', id] as const

// ============================================================================
// Hooks
// ============================================================================

/**
 * 询价列表查询 Hook
 *
 * @param params - 查询参数（分页、状态筛选）
 * @returns TanStack Query 结果，包含分页的询价列表
 *
 * @example
 * ```tsx
 * // 基础用法 - 获取第一页询价列表
 * const { data, isLoading, error } = useQuotes()
 *
 * // 带分页参数
 * const { data } = useQuotes({ page: 2, page_size: 20 })
 *
 * // 带状态筛选
 * const { data } = useQuotes({ status: 'running' })
 *
 * // 组合使用
 * const { data } = useQuotes({
 *   page: 1,
 *   page_size: 10,
 *   status: 'success',
 * })
 * ```
 *
 * Requirements: 2.1 (展示询价列表), 2.5 (状态筛选)
 */
export function useQuotes(params?: QuoteListParams) {
  return useQuery<PaginatedResponse<PreservationQuote>>({
    queryKey: quotesQueryKey(params),
    queryFn: () => preservationQuoteApi.list(params),
    // 30 秒内数据视为新鲜，不会自动重新获取
    staleTime: 30 * 1000,
  })
}

export default useQuotes
