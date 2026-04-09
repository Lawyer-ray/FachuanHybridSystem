/**
 * useRecognitionTask Hook
 * 文书识别任务详情查询 hook（带轮询）
 *
 * 使用 TanStack Query v5 实现识别任务详情查询，
 * 支持轮询状态机逻辑：pending/processing 时轮询，完成时停止
 *
 * Requirements: 5.1, 7.2
 */

import { useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'

import { documentRecognitionApi } from '../api'
import type { DocumentRecognitionTask, RecognitionStatus } from '../types'
import { POLLING_INTERVALS } from '../../constants'
import { recognitionTaskQueryKey } from './use-recognition-tasks'

// ============================================================================
// Types
// ============================================================================

/**
 * useRecognitionTask Hook 配置选项
 */
export interface UseRecognitionTaskOptions {
  /** 是否启用轮询（默认 true） */
  enablePolling?: boolean
  /** 轮询间隔（毫秒，默认 2000） */
  pollingInterval?: number
}

// ============================================================================
// Helpers
// ============================================================================

/**
 * 判断是否应该继续轮询
 *
 * 轮询条件：状态为 pending 或 processing 时继续轮询
 * 停止条件：状态为 success 或 failed 时停止
 *
 * @param status - 识别任务状态
 * @returns 是否应该继续轮询
 *
 * Requirements: 7.2
 */
export const shouldPoll = (status: RecognitionStatus): boolean =>
  status === 'pending' || status === 'processing'

/**
 * 判断任务是否已完成
 *
 * @param status - 识别任务状态
 * @returns 是否已完成
 */
export const isCompleted = (status: RecognitionStatus): boolean =>
  status === 'success' || status === 'failed'

// ============================================================================
// Hook
// ============================================================================

/**
 * 识别任务详情查询 Hook（带轮询）
 *
 * 自动轮询 pending/processing 状态的任务，完成后停止轮询。
 * 支持轮询超时处理（5 分钟）。
 *
 * @param id - 识别任务 ID
 * @param options - 配置选项
 * @returns TanStack Query 结果，包含识别任务详情
 *
 * @example
 * ```tsx
 * // 基础用法 - 自动轮询
 * const { data: task, isLoading, error } = useRecognitionTask(123)
 *
 * // 禁用轮询
 * const { data: task } = useRecognitionTask(123, { enablePolling: false })
 *
 * // 自定义轮询间隔
 * const { data: task } = useRecognitionTask(123, { pollingInterval: 5000 })
 *
 * // 在详情页中使用
 * function RecognitionDetailPage() {
 *   const { id } = useParams<{ id: string }>()
 *   const { data: task, isLoading, error } = useRecognitionTask(Number(id))
 *
 *   if (isLoading) return <Loading />
 *   if (error) return <Error error={error} />
 *   if (!task) return <NotFound />
 *
 *   return <RecognitionDetail task={task} />
 * }
 * ```
 *
 * Requirements: 5.1 (获取详情), 7.2 (轮询)
 */
export function useRecognitionTask(id: number, options?: UseRecognitionTaskOptions) {
  const {
    enablePolling = true,
    pollingInterval = POLLING_INTERVALS.RECOGNITION_PROCESSING,
  } = options ?? {}

  // 记录轮询开始时间，用于超时检测
  const pollingStartTime = useRef<number | null>(null)

  return useQuery<DocumentRecognitionTask>({
    queryKey: recognitionTaskQueryKey(id),
    queryFn: async () => {
      const task = await documentRecognitionApi.getTask(id)

      // 如果任务正在处理且尚未记录开始时间，记录当前时间
      if (shouldPoll(task.status) && pollingStartTime.current === null) {
        pollingStartTime.current = Date.now()
      }

      // 如果任务已完成，重置轮询开始时间
      if (isCompleted(task.status)) {
        pollingStartTime.current = null
      }

      return task
    },
    // 只有当 id 存在且有效时才启用查询
    enabled: !!id && id > 0,
    // 30 秒内数据视为新鲜（非轮询状态时）
    staleTime: 30 * 1000,
    /**
     * 轮询间隔配置
     *
     * TanStack Query v5 的 refetchInterval 可以是一个函数，
     * 根据当前数据状态动态决定是否继续轮询。
     *
     * Requirements: 7.2 (pending/processing 时每 2 秒轮询)
     */
    refetchInterval: (query) => {
      // 如果禁用轮询，返回 false
      if (!enablePolling) {
        return false
      }

      const data = query.state.data

      // 如果没有数据，不轮询
      if (!data) {
        return false
      }

      // 如果任务已完成，停止轮询
      if (!shouldPoll(data.status)) {
        return false
      }

      // 检查轮询超时（5 分钟）
      if (pollingStartTime.current !== null) {
        const elapsed = Date.now() - pollingStartTime.current
        if (elapsed > POLLING_INTERVALS.POLLING_TIMEOUT) {
          // 超时提示
          toast.warning('任务处理时间过长，请刷新页面查看最新状态')
          pollingStartTime.current = null
          return false
        }
      }

      // 继续轮询
      return pollingInterval
    },
    // 轮询时在后台也继续
    refetchIntervalInBackground: false,
  })
}

export default useRecognitionTask
