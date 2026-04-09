/**
 * useTeams Hook
 * 团队列表查询 hook
 *
 * 使用 TanStack Query 实现列表查询，支持 lawFirmId 和 teamType 筛选参数
 *
 * Requirements: 8.11, 8.19
 */

import { useQuery, keepPreviousData } from '@tanstack/react-query'

import { teamApi } from '../api'
import type { Team, TeamType } from '../types'

/**
 * useTeams 参数接口
 */
export interface UseTeamsParams {
  /** 律所 ID 筛选 */
  lawFirmId?: number
  /** 团队类型筛选（lawyer: 律师团队, biz: 业务团队） */
  teamType?: TeamType
}

/**
 * 团队列表查询 Query Key
 */
export const teamsQueryKey = (params?: UseTeamsParams) => [
  'teams',
  {
    lawFirmId: params?.lawFirmId ?? null,
    teamType: params?.teamType ?? null,
  },
] as const

/**
 * 团队列表查询 Hook
 *
 * @param params - 查询参数（律所 ID、团队类型）
 * @returns TanStack Query 结果，包含团队列表
 *
 * @example
 * ```tsx
 * // 基础用法 - 获取所有团队
 * const { data, isLoading, error } = useTeams()
 *
 * // 按律所筛选
 * const { data } = useTeams({ lawFirmId: 1 })
 *
 * // 按团队类型筛选
 * const { data } = useTeams({ teamType: 'lawyer' })
 *
 * // 组合筛选
 * const { data } = useTeams({ lawFirmId: 1, teamType: 'biz' })
 * ```
 *
 * Requirements: 8.11 (获取团队列表), 8.19 (TanStack Query)
 */
export function useTeams(params?: UseTeamsParams) {
  const { lawFirmId, teamType } = params ?? {}

  return useQuery<Team[]>({
    queryKey: teamsQueryKey(params),
    queryFn: async () => {
      return teamApi.list({
        law_firm_id: lawFirmId,
        team_type: teamType,
      })
    },
    // 保持上一次数据，避免筛选时闪烁
    placeholderData: keepPreviousData,
    // 5 分钟内数据视为新鲜，不会自动重新获取
    staleTime: 5 * 60 * 1000,
  })
}

export default useTeams
