/**
 * useLawyer Hook
 * 律师详情查询 hook
 *
 * 使用 TanStack Query 实现单个律师查询
 *
 * Requirements: 8.7, 8.19
 */

import { useQuery } from '@tanstack/react-query'

import { lawyerApi } from '../api'
import type { Lawyer } from '../types'

/**
 * 律师详情查询 Query Key
 *
 * @param id - 律师 ID
 * @returns Query key 数组
 */
export const lawyerQueryKey = (id: string | number) => ['lawyer', id] as const

/**
 * 律师详情查询 Hook
 *
 * @param id - 律师 ID
 * @returns TanStack Query 结果，包含律师详情
 *
 * @example
 * ```tsx
 * // 基础用法
 * const { data: lawyer, isLoading, error } = useLawyer('123')
 *
 * // 在详情页中使用
 * function LawyerDetailPage() {
 *   const { id } = useParams<{ id: string }>()
 *   const { data: lawyer, isLoading, error } = useLawyer(id!)
 *
 *   if (isLoading) return <Loading />
 *   if (error) return <Error error={error} />
 *   if (!lawyer) return <NotFound />
 *
 *   return <LawyerDetail lawyer={lawyer} />
 * }
 * ```
 *
 * Requirements: 8.7 (获取律师详情), 8.19 (TanStack Query)
 */
export function useLawyer(id: string) {
  return useQuery<Lawyer>({
    queryKey: lawyerQueryKey(id),
    queryFn: () => lawyerApi.get(id),
    // 只有当 id 存在时才启用查询
    enabled: !!id,
    // 5 分钟内数据视为新鲜，不会自动重新获取
    staleTime: 5 * 60 * 1000,
  })
}

export default useLawyer
