/**
 * useClientMutations Hook
 * 当事人增删改 mutations hook
 *
 * 使用 TanStack Query 实现当事人的创建、更新、删除操作
 * 配置缓存失效策略，确保数据一致性
 *
 * Requirements: 9.3, 9.4, 9.5, 9.6
 */

import { useMutation, useQueryClient, type UseMutationResult } from '@tanstack/react-query'

import { clientApi } from '../api'
import type { Client, ClientInput } from '../types'
import { clientQueryKey } from './use-client'

/**
 * 更新当事人参数接口
 */
export interface UpdateClientParams {
  /** 当事人 ID */
  id: string
  /** 更新的当事人数据 */
  data: ClientInput
}

/**
 * useClientMutations 返回值接口
 */
export interface UseClientMutationsReturn {
  /** 创建当事人 mutation */
  createClient: UseMutationResult<Client, Error, ClientInput>
  /** 更新当事人 mutation */
  updateClient: UseMutationResult<Client, Error, UpdateClientParams>
  /** 删除当事人 mutation */
  deleteClient: UseMutationResult<void, Error, string>
}

/**
 * 当事人增删改 Mutations Hook
 *
 * 提供创建、更新、删除当事人的 mutation 操作，
 * 并在操作成功后自动失效相关缓存。
 *
 * @returns 包含 createClient、updateClient、deleteClient 三个 mutation 的对象
 *
 * @example
 * ```tsx
 * // 基础用法
 * const { createClient, updateClient, deleteClient } = useClientMutations()
 *
 * // 创建当事人
 * createClient.mutate({
 *   name: '张三',
 *   client_type: 'natural',
 *   phone: '13800138000',
 * }, {
 *   onSuccess: (client) => {
 *     toast.success('创建成功')
 *     navigate(`/admin/clients/${client.id}`)
 *   },
 *   onError: (error) => {
 *     toast.error('创建失败')
 *   },
 * })
 *
 * // 更新当事人
 * updateClient.mutate({
 *   id: '123',
 *   data: { name: '李四', client_type: 'natural' },
 * })
 *
 * // 删除当事人
 * deleteClient.mutate('123', {
 *   onSuccess: () => {
 *     toast.success('删除成功')
 *     navigate('/admin/clients')
 *   },
 * })
 * ```
 *
 * Requirements: 9.3 (创建), 9.4 (更新), 9.5 (删除), 9.6 (TanStack Query)
 */
export function useClientMutations(): UseClientMutationsReturn {
  const queryClient = useQueryClient()

  /**
   * 创建当事人 Mutation
   * POST /api/v1/client/clients
   *
   * Requirements: 9.3
   */
  const createClient = useMutation<Client, Error, ClientInput>({
    mutationFn: (data: ClientInput) => clientApi.create(data),
    onSuccess: () => {
      // 创建成功后，失效列表缓存以刷新数据
      queryClient.invalidateQueries({
        queryKey: ['clients'],
      })
    },
  })

  /**
   * 更新当事人 Mutation
   * PUT /api/v1/client/clients/{id}
   *
   * Requirements: 9.4
   */
  const updateClient = useMutation<Client, Error, UpdateClientParams>({
    mutationFn: ({ id, data }: UpdateClientParams) => clientApi.update(id, data),
    onSuccess: (updatedClient, { id }) => {
      // 更新成功后，失效列表缓存和该当事人的详情缓存
      queryClient.invalidateQueries({
        queryKey: ['clients'],
      })
      queryClient.invalidateQueries({
        queryKey: clientQueryKey(id),
      })
      // 可选：直接更新缓存中的数据，避免额外请求
      queryClient.setQueryData(clientQueryKey(id), updatedClient)
    },
  })

  /**
   * 删除当事人 Mutation
   * DELETE /api/v1/client/clients/{id}
   *
   * Requirements: 9.5
   */
  const deleteClient = useMutation<void, Error, string>({
    mutationFn: (id: string) => clientApi.delete(id),
    onSuccess: (_, id) => {
      // 删除成功后，失效列表缓存
      queryClient.invalidateQueries({
        queryKey: ['clients'],
      })
      // 移除该当事人的详情缓存
      queryClient.removeQueries({
        queryKey: clientQueryKey(id),
      })
    },
  })

  return {
    createClient,
    updateClient,
    deleteClient,
  }
}

export default useClientMutations
