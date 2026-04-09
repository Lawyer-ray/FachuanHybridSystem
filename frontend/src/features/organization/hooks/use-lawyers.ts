/**
 * useLawyers Hook
 * 律师列表查询 hook
 *
 * 使用 TanStack Query 实现列表查询，支持搜索参数
 *
 * Requirements: 8.6, 8.19
 */

import { useQuery, keepPreviousData } from '@tanstack/react-query'

import { lawyerApi } from '../api'
import type { Lawyer } from '../types'

/**
 * useLawyers 参数接口
 */
export interface UseLawyersParams {
  /** 搜索关键词（支持用户名、真实姓名、手机号） */
  search?: string
}

/**
 * 律师列表查询 Query Key
 */
export const lawyersQueryKey = (params?: UseLawyersParams) => [
  'lawyers',
  {
    search: params?.search ?? '',
  },
] as const

/**
 * 律师列表查询 Hook
 *
 * @param params - 查询参数（搜索）
 * @returns TanStack Query 结果，包含律师列表
 *
 * @example
 * ```tsx
 * // 基础用法
 * const { data, isLoading, error } = useLawyers()
 *
 * // 带搜索
 * const { data } = useLawyers({ search: '张三' })
 * ```
 *
 * Requirements: 8.6 (获取律师列表), 8.19 (TanStack Query)
 */
export function useLawyers(params?: UseLawyersParams) {
  const { search } = params ?? {}

  return useQuery<Lawyer[]>({
    queryKey: lawyersQueryKey(params),
    queryFn: async () => {
      return lawyerApi.list({
        search: search || undefined,
      })
    },
    // 保持上一次数据，避免搜索时闪烁
    placeholderData: keepPreviousData,
    // 5 分钟内数据视为新鲜，不会自动重新获取
    staleTime: 5 * 60 * 1000,
  })
}

export default useLawyers
