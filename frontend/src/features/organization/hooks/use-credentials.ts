/**
 * useCredentials Hook
 * 凭证列表查询 hook
 *
 * 使用 TanStack Query 实现列表查询，支持 lawyerId 和 lawyerName 筛选参数
 *
 * Requirements: 8.15, 8.19
 */

import { useQuery, keepPreviousData } from '@tanstack/react-query'

import { credentialApi } from '../api'
import type { AccountCredential } from '../types'

/**
 * useCredentials 参数接口
 */
export interface UseCredentialsParams {
  /** 律师 ID 筛选 */
  lawyerId?: number
  /** 律师姓名筛选 */
  lawyerName?: string
}

/**
 * 凭证列表查询 Query Key
 */
export const credentialsQueryKey = (params?: UseCredentialsParams) => [
  'credentials',
  {
    lawyerId: params?.lawyerId ?? null,
    lawyerName: params?.lawyerName ?? null,
  },
] as const

/**
 * 凭证列表查询 Hook
 *
 * @param params - 查询参数（律师 ID、律师姓名）
 * @returns TanStack Query 结果，包含凭证列表
 *
 * @example
 * ```tsx
 * // 基础用法 - 获取所有凭证
 * const { data, isLoading, error } = useCredentials()
 *
 * // 按律师 ID 筛选
 * const { data } = useCredentials({ lawyerId: 1 })
 *
 * // 按律师姓名筛选
 * const { data } = useCredentials({ lawyerName: '张三' })
 *
 * // 组合筛选
 * const { data } = useCredentials({ lawyerId: 1, lawyerName: '张三' })
 * ```
 *
 * Requirements: 8.15 (获取凭证列表), 8.19 (TanStack Query)
 */
export function useCredentials(params?: UseCredentialsParams) {
  const { lawyerId, lawyerName } = params ?? {}

  return useQuery<AccountCredential[]>({
    queryKey: credentialsQueryKey(params),
    queryFn: async () => {
      return credentialApi.list({
        lawyer_id: lawyerId,
        lawyer_name: lawyerName,
      })
    },
    // 保持上一次数据，避免筛选时闪烁
    placeholderData: keepPreviousData,
    // 5 分钟内数据视为新鲜，不会自动重新获取
    staleTime: 5 * 60 * 1000,
  })
}

export default useCredentials
