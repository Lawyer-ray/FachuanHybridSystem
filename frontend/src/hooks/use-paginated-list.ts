/**
 * 通用客户端分页列表 Hook
 *
 * 抽象了列表页的通用模式：
 * - 页码状态管理
 * - 搜索状态（变更时自动重置到第一页）
 * - 客户端分页（全量获取 + 切片）
 * - PageFooter props 输出
 */

import { useState, useCallback } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'

interface PaginatedResult<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
  totalPages: number
}

interface UsePaginatedListOptions<T, F> {
  /** TanStack Query 缓存 key 的第一段，如 'clients' */
  queryKey: string
  /** 获取全量列表的 API 函数 */
  fetchAll: (filters: F) => Promise<T[]>
  /** 当前筛选参数（由组件维护） */
  filters: F
  /** 每页条数，默认 20 */
  pageSize?: number
  /** 缓存时间（毫秒），默认 2 分钟 */
  staleTime?: number
}

interface UsePaginatedListReturn<T> {
  data: PaginatedResult<T>
  isLoading: boolean
  page: number
  setPage: (page: number) => void
  /** 创建一个带页码重置的值变更回调 */
  withPageReset: <V>(setter: (v: V) => void) => (v: V) => void
}

export function usePaginatedList<T, F extends Record<string, unknown>>({
  queryKey,
  fetchAll,
  filters,
  pageSize = 20,
  staleTime = 2 * 60 * 1000,
}: UsePaginatedListOptions<T, F>): UsePaginatedListReturn<T> {
  const [page, setPage] = useState(1)

  const query = useQuery<PaginatedResult<T>>({
    queryKey: [queryKey, filters, page, pageSize],
    queryFn: async () => {
      const all = await fetchAll(filters)
      const total = all.length
      const totalPages = Math.ceil(total / pageSize) || 1
      const start = (page - 1) * pageSize
      return {
        items: all.slice(start, start + pageSize),
        total,
        page,
        pageSize,
        totalPages,
      }
    },
    placeholderData: keepPreviousData,
    staleTime,
  })

  const withPageReset = useCallback(
    <V,>(setter: (v: V) => void) =>
      (v: V) => {
        setter(v)
        setPage(1)
      },
    [],
  )

  return {
    data: query.data ?? { items: [] as T[], total: 0, page: 1, pageSize, totalPages: 0 },
    isLoading: query.isLoading,
    page,
    setPage,
    withPageReset,
  }
}
