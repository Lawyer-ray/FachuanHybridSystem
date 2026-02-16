/**
 * useLawFirmMutations Hook
 * 律所增删改 mutations hook
 *
 * 使用 TanStack Query 实现律所的创建、更新、删除操作
 * 配置缓存失效策略，确保数据一致性
 *
 * Requirements: 8.3, 8.4, 8.5, 8.19
 */

import { useMutation, useQueryClient, type UseMutationResult } from '@tanstack/react-query'

import { lawFirmApi } from '../api'
import type { LawFirm, LawFirmInput, LawFirmUpdateInput } from '../types'
import { lawFirmQueryKey } from './use-lawfirm'
import { lawFirmsQueryKey } from './use-lawfirms'

/**
 * 更新律所参数接口
 */
export interface UpdateLawFirmParams {
  /** 律所 ID */
  id: number
  /** 更新的律所数据 */
  data: LawFirmUpdateInput
}

/**
 * useLawFirmMutations 返回值接口
 */
export interface UseLawFirmMutationsReturn {
  /** 创建律所 mutation */
  createLawFirm: UseMutationResult<LawFirm, Error, LawFirmInput>
  /** 更新律所 mutation */
  updateLawFirm: UseMutationResult<LawFirm, Error, UpdateLawFirmParams>
  /** 删除律所 mutation */
  deleteLawFirm: UseMutationResult<void, Error, number>
}

/**
 * 律所增删改 Mutations Hook
 *
 * 提供创建、更新、删除律所的 mutation 操作，
 * 并在操作成功后自动失效相关缓存。
 *
 * @returns 包含 createLawFirm、updateLawFirm、deleteLawFirm 三个 mutation 的对象
 *
 * @example
 * ```tsx
 * // 基础用法
 * const { createLawFirm, updateLawFirm, deleteLawFirm } = useLawFirmMutations()
 *
 * // 创建律所
 * createLawFirm.mutate({
 *   name: '北京某某律师事务所',
 *   address: '北京市朝阳区xxx',
 *   phone: '010-12345678',
 * }, {
 *   onSuccess: (lawFirm) => {
 *     toast.success('创建成功')
 *     navigate(`/admin/organization/lawfirms/${lawFirm.id}`)
 *   },
 *   onError: (error) => {
 *     toast.error('创建失败')
 *   },
 * })
 *
 * // 更新律所
 * updateLawFirm.mutate({
 *   id: 123,
 *   data: { name: '更新后的律所名称' },
 * })
 *
 * // 删除律所
 * deleteLawFirm.mutate(123, {
 *   onSuccess: () => {
 *     toast.success('删除成功')
 *     navigate('/admin/organization/lawfirms')
 *   },
 * })
 * ```
 *
 * Requirements: 8.3 (创建), 8.4 (更新), 8.5 (删除), 8.19 (TanStack Query)
 */
export function useLawFirmMutations(): UseLawFirmMutationsReturn {
  const queryClient = useQueryClient()

  /**
   * 创建律所 Mutation
   * POST /api/v1/organization/lawfirms
   *
   * Requirements: 8.3
   */
  const createLawFirm = useMutation<LawFirm, Error, LawFirmInput>({
    mutationFn: (data: LawFirmInput) => lawFirmApi.create(data),
    onSuccess: () => {
      // 创建成功后，失效列表缓存以刷新数据
      queryClient.invalidateQueries({
        queryKey: lawFirmsQueryKey,
      })
    },
  })

  /**
   * 更新律所 Mutation
   * PUT /api/v1/organization/lawfirms/{id}
   *
   * Requirements: 8.4
   */
  const updateLawFirm = useMutation<LawFirm, Error, UpdateLawFirmParams>({
    mutationFn: ({ id, data }: UpdateLawFirmParams) => lawFirmApi.update(id, data),
    onSuccess: (updatedLawFirm, { id }) => {
      // 更新成功后，失效列表缓存和该律所的详情缓存
      queryClient.invalidateQueries({
        queryKey: lawFirmsQueryKey,
      })
      queryClient.invalidateQueries({
        queryKey: lawFirmQueryKey(id),
      })
      // 可选：直接更新缓存中的数据，避免额外请求
      queryClient.setQueryData(lawFirmQueryKey(id), updatedLawFirm)
    },
  })

  /**
   * 删除律所 Mutation
   * DELETE /api/v1/organization/lawfirms/{id}
   *
   * Requirements: 8.5
   */
  const deleteLawFirm = useMutation<void, Error, number>({
    mutationFn: (id: number) => lawFirmApi.delete(id),
    onSuccess: (_, id) => {
      // 删除成功后，失效列表缓存
      queryClient.invalidateQueries({
        queryKey: lawFirmsQueryKey,
      })
      // 移除该律所的详情缓存
      queryClient.removeQueries({
        queryKey: lawFirmQueryKey(id),
      })
    },
  })

  return {
    createLawFirm,
    updateLawFirm,
    deleteLawFirm,
  }
}

export default useLawFirmMutations
