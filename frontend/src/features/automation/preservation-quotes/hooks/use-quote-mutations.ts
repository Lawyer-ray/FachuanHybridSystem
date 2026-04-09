/**
 * useQuoteMutations Hook
 * 财产保全询价 Mutation Hooks
 *
 * 使用 TanStack Query v5 实现询价的创建、执行、重试操作
 * 配置缓存失效策略，确保数据一致性
 * 处理成功/失败 toast 提示
 *
 * Requirements: 3.6, 4.5, 4.9, 9.1, 9.3
 */

import { useMutation, useQueryClient, type UseMutationResult } from '@tanstack/react-query'
import { toast } from 'sonner'

import { preservationQuoteApi } from '../api'
import type { PreservationQuote, PreservationQuoteCreate } from '../types'
import { quoteQueryKey } from './use-quotes'

// ============================================================================
// Types
// ============================================================================

/**
 * useCreateQuote 返回值类型
 */
export type UseCreateQuoteResult = UseMutationResult<
  PreservationQuote,
  Error,
  PreservationQuoteCreate
>

/**
 * useExecuteQuote 返回值类型
 */
export type UseExecuteQuoteResult = UseMutationResult<PreservationQuote, Error, number>

/**
 * useRetryQuote 返回值类型
 */
export type UseRetryQuoteResult = UseMutationResult<PreservationQuote, Error, number>

// ============================================================================
// Hooks
// ============================================================================

/**
 * 创建询价任务 Mutation Hook
 *
 * POST /api/v1/automation/preservation-quotes/
 *
 * @returns TanStack Query Mutation 结果
 *
 * @example
 * ```tsx
 * const createQuote = useCreateQuote()
 *
 * // 创建询价
 * createQuote.mutate({
 *   preserve_amount: 100000,
 *   corp_id: 'corp_123',
 *   category_id: 'cat_456',
 *   credential_id: 1,
 * })
 *
 * // 带回调
 * createQuote.mutate(data, {
 *   onSuccess: (quote) => {
 *     navigate(`/admin/automation/preservation-quotes/${quote.id}`)
 *   },
 * })
 * ```
 *
 * Requirements: 3.6 (创建询价任务并显示成功提示)
 * Requirements: 9.1 (API 请求失败显示 toast 错误提示)
 * Requirements: 9.3 (操作成功显示成功提示)
 */
export function useCreateQuote(): UseCreateQuoteResult {
  const queryClient = useQueryClient()

  return useMutation<PreservationQuote, Error, PreservationQuoteCreate>({
    mutationFn: (data: PreservationQuoteCreate) => preservationQuoteApi.create(data),
    onSuccess: () => {
      // 创建成功后，失效所有询价列表缓存以刷新数据
      queryClient.invalidateQueries({
        queryKey: ['preservation-quotes'],
      })
      // 显示成功提示 (Requirements: 9.3)
      toast.success('询价任务创建成功')
    },
    onError: (error) => {
      // 显示错误提示 (Requirements: 9.1)
      toast.error(`创建询价失败: ${error.message}`)
    },
  })
}

/**
 * 执行询价任务 Mutation Hook
 *
 * POST /api/v1/automation/preservation-quotes/{id}/execute/
 *
 * 执行成功后任务状态变为 running，开始轮询状态更新
 *
 * @returns TanStack Query Mutation 结果
 *
 * @example
 * ```tsx
 * const executeQuote = useExecuteQuote()
 *
 * // 执行询价
 * executeQuote.mutate(quoteId)
 *
 * // 带回调
 * executeQuote.mutate(quoteId, {
 *   onSuccess: (quote) => {
 *     console.log('开始执行询价，状态:', quote.status)
 *   },
 * })
 * ```
 *
 * Requirements: 4.5 (调用执行 API 并开始轮询状态)
 * Requirements: 9.1 (API 请求失败显示 toast 错误提示)
 * Requirements: 9.3 (操作成功显示成功提示)
 */
export function useExecuteQuote(): UseExecuteQuoteResult {
  const queryClient = useQueryClient()

  return useMutation<PreservationQuote, Error, number>({
    mutationFn: (id: number) => preservationQuoteApi.execute(id),
    onSuccess: (updatedQuote, id) => {
      // 更新缓存中的询价详情数据
      queryClient.setQueryData(quoteQueryKey(id), updatedQuote)
      // 失效列表缓存以刷新状态
      queryClient.invalidateQueries({
        queryKey: ['preservation-quotes'],
      })
      // 显示成功提示 (Requirements: 9.3)
      toast.success('询价任务开始执行')
    },
    onError: (error) => {
      // 显示错误提示 (Requirements: 9.1)
      toast.error(`执行询价失败: ${error.message}`)
    },
  })
}

/**
 * 重试询价任务 Mutation Hook
 *
 * POST /api/v1/automation/preservation-quotes/{id}/retry/
 *
 * 重试成功后任务状态变为 running，重新开始轮询状态更新
 *
 * @returns TanStack Query Mutation 结果
 *
 * @example
 * ```tsx
 * const retryQuote = useRetryQuote()
 *
 * // 重试询价
 * retryQuote.mutate(quoteId)
 *
 * // 带回调
 * retryQuote.mutate(quoteId, {
 *   onSuccess: (quote) => {
 *     console.log('开始重试询价，状态:', quote.status)
 *   },
 * })
 * ```
 *
 * Requirements: 4.9 (调用重试 API 并重新开始轮询)
 * Requirements: 9.1 (API 请求失败显示 toast 错误提示)
 * Requirements: 9.3 (操作成功显示成功提示)
 */
export function useRetryQuote(): UseRetryQuoteResult {
  const queryClient = useQueryClient()

  return useMutation<PreservationQuote, Error, number>({
    mutationFn: (id: number) => preservationQuoteApi.retry(id),
    onSuccess: (updatedQuote, id) => {
      // 更新缓存中的询价详情数据
      queryClient.setQueryData(quoteQueryKey(id), updatedQuote)
      // 失效列表缓存以刷新状态
      queryClient.invalidateQueries({
        queryKey: ['preservation-quotes'],
      })
      // 显示成功提示 (Requirements: 9.3)
      toast.success('询价任务开始重试')
    },
    onError: (error) => {
      // 显示错误提示 (Requirements: 9.1)
      toast.error(`重试询价失败: ${error.message}`)
    },
  })
}

export default {
  useCreateQuote,
  useExecuteQuote,
  useRetryQuote,
}
