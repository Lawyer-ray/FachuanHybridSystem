/**
 * useTeamMutations Hook
 * 团队增删改 mutations hook
 *
 * 使用 TanStack Query 实现团队的创建、更新、删除操作
 * 配置缓存失效策略，确保数据一致性
 *
 * Requirements: 8.12, 8.13, 8.14, 8.19
 */

import { useMutation, useQueryClient, type UseMutationResult } from '@tanstack/react-query'

import { teamApi } from '../api'
import type { Team, TeamInput } from '../types'

/**
 * 更新团队参数接口
 */
export interface UpdateTeamParams {
  /** 团队 ID */
  id: number
  /** 更新的团队数据 */
  data: TeamInput
}

/**
 * useTeamMutations 返回值接口
 */
export interface UseTeamMutationsReturn {
  /** 创建团队 mutation */
  createTeam: UseMutationResult<Team, Error, TeamInput>
  /** 更新团队 mutation */
  updateTeam: UseMutationResult<Team, Error, UpdateTeamParams>
  /** 删除团队 mutation */
  deleteTeam: UseMutationResult<void, Error, number>
}

export function useTeamMutations(): UseTeamMutationsReturn {
  const queryClient = useQueryClient()

  const createTeam = useMutation<Team, Error, TeamInput>({
    mutationFn: (data: TeamInput) => teamApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({
        predicate: (query) => query.queryKey[0] === 'teams',
      })
    },
  })

  const updateTeam = useMutation<Team, Error, UpdateTeamParams>({
    mutationFn: ({ id, data }: UpdateTeamParams) => teamApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({
        predicate: (query) => query.queryKey[0] === 'teams',
      })
    },
  })

  const deleteTeam = useMutation<void, Error, number>({
    mutationFn: (id: number) => teamApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({
        predicate: (query) => query.queryKey[0] === 'teams',
      })
    },
  })

  return {
    createTeam,
    updateTeam,
    deleteTeam,
  }
}

export default useTeamMutations
