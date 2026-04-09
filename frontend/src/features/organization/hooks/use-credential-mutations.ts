/**
 * useCredentialMutations Hook
 * 凭证增删改 mutations hook
 *
 * 使用 TanStack Query 实现凭证的创建、更新、删除操作
 * 配置缓存失效策略，确保数据一致性
 *
 * Requirements: 8.16, 8.17, 8.18, 8.19
 */

import { useMutation, useQueryClient, type UseMutationResult } from '@tanstack/react-query'

import { credentialApi } from '../api'
import type { AccountCredential, CredentialInput, CredentialUpdateInput } from '../types'

/**
 * 更新凭证参数接口
 */
export interface UpdateCredentialParams {
  /** 凭证 ID */
  id: number
  /** 更新的凭证数据 */
  data: CredentialUpdateInput
}

/**
 * useCredentialMutations 返回值接口
 */
export interface UseCredentialMutationsReturn {
  /** 创建凭证 mutation */
  createCredential: UseMutationResult<AccountCredential, Error, CredentialInput>
  /** 更新凭证 mutation */
  updateCredential: UseMutationResult<AccountCredential, Error, UpdateCredentialParams>
  /** 删除凭证 mutation */
  deleteCredential: UseMutationResult<void, Error, number>
}

/**
 * 凭证增删改 Mutations Hook
 *
 * 提供创建、更新、删除凭证的 mutation 操作，
 * 并在操作成功后自动失效相关缓存。
 *
 * @returns 包含 createCredential、updateCredential、deleteCredential 三个 mutation 的对象
 *
 * @example
 * ```tsx
 * // 基础用法
 * const { createCredential, updateCredential, deleteCredential } = useCredentialMutations()
 *
 * // 创建凭证
 * createCredential.mutate({
 *   lawyer_id: 1,
 *   site_name: '法院系统',
 *   url: 'https://court.example.com',
 *   account: 'lawyer001',
 *   password: '<REDACTED>',
 * }, {
 *   onSuccess: (credential) => {
 *     toast.success('创建成功')
 *     onOpenChange(false)
 *   },
 *   onError: (error) => {
 *     toast.error('创建失败')
 *   },
 * })
 *
 * // 更新凭证
 * updateCredential.mutate({
 *   id: 123,
 *   data: { site_name: '更新后的网站名称', account: 'new_account' },
 * })
 *
 * // 删除凭证
 * deleteCredential.mutate(123, {
 *   onSuccess: () => {
 *     toast.success('删除成功')
 *   },
 * })
 * ```
 *
 * Requirements: 8.16 (创建), 8.17 (更新), 8.18 (删除), 8.19 (TanStack Query)
 */
export function useCredentialMutations(): UseCredentialMutationsReturn {
  const queryClient = useQueryClient()

  /**
   * 创建凭证 Mutation
   * POST /api/v1/organization/credentials
   *
   * Requirements: 8.16
   */
  const createCredential = useMutation<AccountCredential, Error, CredentialInput>({
    mutationFn: (data: CredentialInput) => credentialApi.create(data),
    onSuccess: () => {
      // 创建成功后，失效所有凭证列表缓存以刷新数据
      // 使用 predicate 匹配所有以 'credentials' 开头的查询
      queryClient.invalidateQueries({
        predicate: (query) => query.queryKey[0] === 'credentials',
      })
    },
  })

  /**
   * 更新凭证 Mutation
   * PUT /api/v1/organization/credentials/{id}
   *
   * Requirements: 8.17
   */
  const updateCredential = useMutation<AccountCredential, Error, UpdateCredentialParams>({
    mutationFn: ({ id, data }: UpdateCredentialParams) => credentialApi.update(id, data),
    onSuccess: () => {
      // 更新成功后，失效所有凭证列表缓存
      // 使用 predicate 匹配所有以 'credentials' 开头的查询
      queryClient.invalidateQueries({
        predicate: (query) => query.queryKey[0] === 'credentials',
      })
    },
  })

  /**
   * 删除凭证 Mutation
   * DELETE /api/v1/organization/credentials/{id}
   *
   * Requirements: 8.18
   */
  const deleteCredential = useMutation<void, Error, number>({
    mutationFn: (id: number) => credentialApi.delete(id),
    onSuccess: () => {
      // 删除成功后，失效所有凭证列表缓存
      // 使用 predicate 匹配所有以 'credentials' 开头的查询
      queryClient.invalidateQueries({
        predicate: (query) => query.queryKey[0] === 'credentials',
      })
    },
  })

  return {
    createCredential,
    updateCredential,
    deleteCredential,
  }
}

export default useCredentialMutations
