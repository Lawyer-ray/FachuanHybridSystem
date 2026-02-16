/**
 * useClient Hook
 * 当事人详情查询 hook
 *
 * 使用 TanStack Query 实现单个当事人查询
 *
 * Requirements: 9.2, 9.6
 */

import { useQuery } from '@tanstack/react-query'

import { clientApi } from '../api'
import type { Client } from '../types'

/**
 * 当事人详情查询 Query Key
 *
 * @param id - 当事人 ID
 * @returns Query key 数组
 */
export const clientQueryKey = (id: string | number) => ['client', id] as const

/**
 * 当事人详情查询 Hook
 *
 * @param id - 当事人 ID
 * @returns TanStack Query 结果，包含当事人详情
 *
 * @example
 * ```tsx
 * // 基础用法
 * const { data: client, isLoading, error } = useClient('123')
 *
 * // 在详情页中使用
 * function ClientDetailPage() {
 *   const { id } = useParams<{ id: string }>()
 *   const { data: client, isLoading, error } = useClient(id!)
 *
 *   if (isLoading) return <Loading />
 *   if (error) return <Error error={error} />
 *   if (!client) return <NotFound />
 *
 *   return <ClientDetail client={client} />
 * }
 * ```
 *
 * Requirements: 9.2 (获取当事人详情), 9.6 (TanStack Query)
 */
export function useClient(id: string) {
  return useQuery<Client>({
    queryKey: clientQueryKey(id),
    queryFn: () => clientApi.get(id),
    // 只有当 id 存在时才启用查询
    enabled: !!id,
    // 5 分钟内数据视为新鲜，不会自动重新获取
    staleTime: 5 * 60 * 1000,
  })
}

export default useClient
