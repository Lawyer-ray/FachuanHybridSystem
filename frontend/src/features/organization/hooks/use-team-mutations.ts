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

/**
 * 团队增删改 Mutations Hook
 *
 * 提供创建、更新、删除团队的 mutation 操作，
 * 并在操作成功后自动失效相关缓存。
 *
 * @returns 包含 createTeam、updateTeam、deleteTeam 三个 mutation 的对象
 *
 * @example
 * ```tsx
 * // 基础用法
 * const { createTeam, updateTeam, deleteTeam } = useTeamMutations()
 *
 * // 创建团队
 * createTeam.mutate({
 *   name: '诉讼一组',
 *   team_type: 'lawyer',
 *   law_firm_id: 1,
 * }, {
 *   onSuccess: (team) => {
 *     toast.success('创建成功')
 *     onOpenChange(false)
 *   },
 *   onError: (error) => {
 *     toast.error('创建失败')
 *   },
 * })
 *
 * // 更新团队
 * updateTeam.mutate({
 *   id: 123,
 *   data: { name: '更新后的团队名称', team_type: 'biz', law_firm_id: 1 },
 * })
 *
 * // 删除团队
 * deleteTeam.mutate(123, {
 *   onSuccess: () => {
 *     toast.success('删除成功')
 *   },
 * })
 * ```
 *
 * Requirements: 8.12 (创建), 8.13 (更新), 8.14 (删除), 8.19 (TanStack Query)
 */
export function useTeamMutations(): UseTeamMutationsReturn {
  const queryClient = useQueryClient()

  /**
   * 创建团队 Mutation
   * POST /api/v1/organization/teams
   *
   * Requirements: 8.12
   */
  const createTeam = useMutation<Team, Error, TeamInput>({
    mutationFn: (data: TeamInput) => teamApi.create(data),
    onSuccess: () => {
      // 创建成功后，失效所有团队列表缓存以刷新数据
      // 使用 predicate 匹配所有以 'teams' 开头的查询
      queryClient.invalidateQueries({
        predicate: (query) => query.queryKey[0] === 'teams',
      })
    },
  })

  /**
   * 更新团队 Mutation
   * PUT /api/v1/organization/teams/{id}
   *
   * Requirements: 8.13
   */
  const updateTeam = useMutation<Team, Error, UpdateTeamParams>({
    mutationFn: ({ id, data }: UpdateTeamParams) => teamApi.update(id, data),
    onSuccess: () => {
      // 更新成功后，失效所有团队列表缓存
      // 使用 predicate 匹配所有以 'teams' 开头的查询
      queryClient.invalidateQueries({
        predicate: (query) => query.queryKey[0] === 'teams',
      })
    },
  })

  /**
   * 删除团队 Mutation
   * DELETE /api/v1/organization/teams/{id}
   *
   * Requirements: 8.14
   */
  const deleteTeam = useMutation<void, Error, number>({
    mutationFn: (id: number) => teamApi.delete(id),
    onSuccess: () => {
      // 删除成功后，失效所有团队列表缓存
      // 使用 predicate 匹配所有以 'teams' 开头的查询
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
