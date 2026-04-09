/**
 * useLawFirm Hook
 * 律所详情查询 hook
 *
 * 使用 TanStack Query 实现单个律所查询
 *
 * Requirements: 8.2, 8.19
 */

import { useQuery } from '@tanstack/react-query'

import { lawFirmApi } from '../api'
import type { LawFirm } from '../types'

/**
 * 律所详情查询 Query Key
 *
 * @param id - 律所 ID
 * @returns Query key 数组
 */
export const lawFirmQueryKey = (id: string | number) => ['lawFirm', id] as const

/**
 * 律所详情查询 Hook
 *
 * @param id - 律所 ID
 * @returns TanStack Query 结果，包含律所详情
 *
 * @example
 * ```tsx
 * // 基础用法
 * const { data: lawFirm, isLoading, error } = useLawFirm('123')
 *
 * // 在详情页中使用
 * function LawFirmDetailPage() {
 *   const { id } = useParams<{ id: string }>()
 *   const { data: lawFirm, isLoading, error } = useLawFirm(id!)
 *
 *   if (isLoading) return <Loading />
 *   if (error) return <Error error={error} />
 *   if (!lawFirm) return <NotFound />
 *
 *   return <LawFirmDetail lawFirm={lawFirm} />
 * }
 * ```
 *
 * Requirements: 8.2 (获取律所详情), 8.19 (TanStack Query)
 */
export function useLawFirm(id: string) {
  return useQuery<LawFirm>({
    queryKey: lawFirmQueryKey(id),
    queryFn: () => lawFirmApi.get(id),
    // 只有当 id 存在时才启用查询
    enabled: !!id,
    // 5 分钟内数据视为新鲜，不会自动重新获取
    staleTime: 5 * 60 * 1000,
  })
}

export default useLawFirm
