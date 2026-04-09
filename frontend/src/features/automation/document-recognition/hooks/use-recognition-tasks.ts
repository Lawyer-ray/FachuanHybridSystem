/**
 * useRecognitionTasks Hook
 * 文书识别任务列表查询 hook
 *
 * 使用 TanStack Query v5 实现识别任务列表查询（带分页和筛选）
 *
 * Requirements: 5.1, 5.5
 */

import { useQuery } from '@tanstack/react-query'

import { documentRecognitionApi, type PaginatedResponse } from '../api'
import type { DocumentRecognitionTask, RecognitionListParams } from '../types'

// ============================================================================
// Query Keys
// ============================================================================

/**
 * 识别任务列表查询 Query Key
 *
 * @param params - 查询参数（分页、状态筛选）
 * @returns Query key 数组
 */
export const recognitionTasksQueryKey = (params?: RecognitionListParams) =>
  [
    'recognition-tasks',
    {
      page: params?.page ?? 1,
      page_size: params?.page_size ?? 10,
      status: params?.status ?? null,
    },
  ] as const

/**
 * 单个识别任务查询 Query Key
 *
 * @param id - 识别任务 ID
 * @returns Query key 数组
 */
export const recognitionTaskQueryKey = (id: number) =>
  ['recognition-task', id] as const

// ============================================================================
// Hooks
// ============================================================================

/**
 * 识别任务列表查询 Hook
 *
 * @param params - 查询参数（分页、状态筛选）
 * @returns TanStack Query 结果，包含分页的识别任务列表
 *
 * @example
 * ```tsx
 * // 基础用法 - 获取第一页识别任务列表
 * const { data, isLoading, error } = useRecognitionTasks()
 *
 * // 带分页参数
 * const { data } = useRecognitionTasks({ page: 2, page_size: 20 })
 *
 * // 带状态筛选
 * const { data } = useRecognitionTasks({ status: 'processing' })
 *
 * // 组合使用
 * const { data } = useRecognitionTasks({
 *   page: 1,
 *   page_size: 10,
 *   status: 'success',
 * })
 * ```
 *
 * Requirements: 5.1 (展示识别任务列表), 5.5 (状态筛选)
 */
export function useRecognitionTasks(params?: RecognitionListParams) {
  return useQuery<PaginatedResponse<DocumentRecognitionTask>>({
    queryKey: recognitionTasksQueryKey(params),
    queryFn: () => documentRecognitionApi.list(params),
    // 30 秒内数据视为新鲜，不会自动重新获取
    staleTime: 30 * 1000,
  })
}

export default useRecognitionTasks
