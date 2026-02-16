/**
 * useLawFirms Hook
 * 律所列表查询 hook
 *
 * 使用 TanStack Query 实现列表查询
 *
 * Requirements: 8.1, 8.19
 */

import { useQuery } from '@tanstack/react-query'

import { lawFirmApi } from '../api'
import type { LawFirm } from '../types'

/**
 * 律所列表查询 Query Key
 */
export const lawFirmsQueryKey = ['lawfirms'] as const

/**
 * 律所列表查询 Hook
 *
 * @returns TanStack Query 结果，包含律所列表
 *
 * @example
 * ```tsx
 * // 基础用法
 * const { data, isLoading, error } = useLawFirms()
 *
 * // 使用数据
 * if (isLoading) return <Spinner />
 * if (error) return <Error message={error.message} />
 * return <LawFirmTable data={data ?? []} />
 * ```
 *
 * Requirements: 8.1 (GET /api/v1/organization/lawfirms), 8.19 (TanStack Query)
 */
export function useLawFirms() {
  return useQuery<LawFirm[]>({
    queryKey: lawFirmsQueryKey,
    queryFn: () => lawFirmApi.list(),
    // 5 分钟内数据视为新鲜，不会自动重新获取
    staleTime: 5 * 60 * 1000,
  })
}

export default useLawFirms
