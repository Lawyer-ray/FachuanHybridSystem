/**
 * useLawyerMutations Hook
 * 律师增删改 mutations hook
 *
 * 使用 TanStack Query 实现律师的创建、更新、删除操作
 * 支持文件上传（执业证 PDF）
 * 配置缓存失效策略，确保数据一致性
 *
 * Requirements: 8.8, 8.9, 8.10, 8.19
 */

import { useMutation, useQueryClient, type UseMutationResult } from '@tanstack/react-query'

import { lawyerApi } from '../api'
import type { Lawyer, LawyerCreateInput, LawyerUpdateInput } from '../types'
import { lawyerQueryKey } from './use-lawyer'
import { lawyersQueryKey } from './use-lawyers'

/**
 * 创建律师参数接口
 */
export interface CreateLawyerParams {
  /** 律师数据 */
  data: LawyerCreateInput
  /** 执业证 PDF 文件（可选） */
  licensePdf?: File
}

/**
 * 更新律师参数接口
 */
export interface UpdateLawyerParams {
  /** 律师 ID */
  id: number
  /** 更新的律师数据 */
  data: LawyerUpdateInput
  /** 执业证 PDF 文件（可选） */
  licensePdf?: File
}

/**
 * useLawyerMutations 返回值接口
 */
export interface UseLawyerMutationsReturn {
  /** 创建律师 mutation */
  createLawyer: UseMutationResult<Lawyer, Error, CreateLawyerParams>
  /** 更新律师 mutation */
  updateLawyer: UseMutationResult<Lawyer, Error, UpdateLawyerParams>
  /** 删除律师 mutation */
  deleteLawyer: UseMutationResult<void, Error, number>
}

/**
 * 律师增删改 Mutations Hook
 *
 * 提供创建、更新、删除律师的 mutation 操作，
 * 支持执业证 PDF 文件上传，
 * 并在操作成功后自动失效相关缓存。
 *
 * @returns 包含 createLawyer、updateLawyer、deleteLawyer 三个 mutation 的对象
 *
 * @example
 * ```tsx
 * // 基础用法
 * const { createLawyer, updateLawyer, deleteLawyer } = useLawyerMutations()
 *
 * // 创建律师（无文件）
 * createLawyer.mutate({
 *   data: {
 *     username: 'zhangsan',
 *     pwd: '<REDACTED>',
 *     real_name: '张三',
 *     mobile_masked: '138****8000',
 *     license_no: '12345678901234567',
 *   },
 * }, {
 *   onSuccess: (lawyer) => {
 *     toast.success('创建成功')
 *     navigate(`/admin/organization/lawyers/${lawyer.id}`)
 *   },
 *   onError: (error) => {
 *     toast.error('创建失败')
 *   },
 * })
 *
 * // 创建律师（带执业证 PDF）
 * createLawyer.mutate({
 *   data: {
 *     username: 'lisi',
 *     pwd: '<REDACTED>',
 *     real_name: '李四',
 *   },
 *   licensePdf: selectedFile,
 * })
 *
 * // 更新律师
 * updateLawyer.mutate({
 *   id: 123,
 *   data: { real_name: '王五', mobile_masked: '139****9000' },
 * })
 *
 * // 更新律师（带新执业证 PDF）
 * updateLawyer.mutate({
 *   id: 123,
 *   data: { real_name: '王五' },
 *   licensePdf: newLicenseFile,
 * })
 *
 * // 删除律师
 * deleteLawyer.mutate(123, {
 *   onSuccess: () => {
 *     toast.success('删除成功')
 *     navigate('/admin/organization/lawyers')
 *   },
 * })
 * ```
 *
 * Requirements: 8.8 (创建), 8.9 (更新), 8.10 (删除), 8.19 (TanStack Query)
 */
export function useLawyerMutations(): UseLawyerMutationsReturn {
  const queryClient = useQueryClient()

  /**
   * 创建律师 Mutation
   * POST /api/v1/organization/lawyers
   *
   * 支持文件上传（执业证 PDF）
   *
   * Requirements: 8.8
   */
  const createLawyer = useMutation<Lawyer, Error, CreateLawyerParams>({
    mutationFn: ({ data, licensePdf }: CreateLawyerParams) =>
      lawyerApi.create(data, licensePdf),
    onSuccess: () => {
      // 创建成功后，失效所有律师列表缓存以刷新数据
      // 使用 predicate 匹配所有以 'lawyers' 开头的查询
      queryClient.invalidateQueries({
        predicate: (query) =>
          Array.isArray(query.queryKey) && query.queryKey[0] === 'lawyers',
      })
    },
  })

  /**
   * 更新律师 Mutation
   * PUT /api/v1/organization/lawyers/{id}
   *
   * 支持文件上传（执业证 PDF）
   *
   * Requirements: 8.9
   */
  const updateLawyer = useMutation<Lawyer, Error, UpdateLawyerParams>({
    mutationFn: ({ id, data, licensePdf }: UpdateLawyerParams) =>
      lawyerApi.update(id, data, licensePdf),
    onSuccess: (updatedLawyer, { id }) => {
      // 更新成功后，失效所有律师列表缓存
      queryClient.invalidateQueries({
        predicate: (query) =>
          Array.isArray(query.queryKey) && query.queryKey[0] === 'lawyers',
      })
      // 失效该律师的详情缓存
      queryClient.invalidateQueries({
        queryKey: lawyerQueryKey(id),
      })
      // 可选：直接更新缓存中的数据，避免额外请求
      queryClient.setQueryData(lawyerQueryKey(id), updatedLawyer)
    },
  })

  /**
   * 删除律师 Mutation
   * DELETE /api/v1/organization/lawyers/{id}
   *
   * Requirements: 8.10
   */
  const deleteLawyer = useMutation<void, Error, number>({
    mutationFn: (id: number) => lawyerApi.delete(id),
    onSuccess: (_, id) => {
      // 删除成功后，失效所有律师列表缓存
      queryClient.invalidateQueries({
        predicate: (query) =>
          Array.isArray(query.queryKey) && query.queryKey[0] === 'lawyers',
      })
      // 移除该律师的详情缓存
      queryClient.removeQueries({
        queryKey: lawyerQueryKey(id),
      })
    },
  })

  return {
    createLawyer,
    updateLawyer,
    deleteLawyer,
  }
}

export default useLawyerMutations
