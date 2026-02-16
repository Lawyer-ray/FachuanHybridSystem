/**
 * useQuote Hook
 * 财产保全询价详情查询 hook（带轮询）
 *
 * 使用 TanStack Query v5 实现询价详情查询，
 * 支持轮询状态机逻辑：running 时轮询，完成时停止
 *
 * Requirements: 2.1, 4.6, 4.7
 */

import { useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'

import { preservationQuoteApi } from '../api'
import type { PreservationQuote, QuoteStatus } from '../types'
import { POLLING_INTERVALS } from '../../constants'
import { quoteQueryKey } from './use-quotes'

// ============================================================================
// Types
// ============================================================================

/**
 * useQuote Hook 配置选项
 */
export interface UseQuoteOptions {
  /** 是否启用轮询（默认 true） */
  enablePolling?: boolean
  /** 轮询间隔（毫秒，默认 3000） */
  pollingInterval?: number
}

// ============================================================================
// Helpers
// ============================================================================

/**
 * 判断是否应该继续轮询
 *
 * 轮询条件：状态为 pending 或 running 时继续轮询
 * 停止条件：状态为 success、partial_success 或 failed 时停止
 *
 * @param status - 询价任务状态
 * @returns 是否应该继续轮询
 *
 * Requirements: 4.6, 4.7
 */
export const shouldPoll = (status: QuoteStatus): boolean =>
  status === 'pending' || status === 'running'

/**
 * 判断任务是否已完成
 *
 * @param status - 询价任务状态
 * @returns 是否已完成
 */
export const isCompleted = (status: QuoteStatus): boolean =>
  status === 'success' || status === 'partial_success' || status === 'failed'

// ============================================================================
// Hook
// ============================================================================

/**
 * 询价详情查询 Hook（带轮询）
 *
 * 自动轮询 running 状态的任务，完成后停止轮询。
 * 支持轮询超时处理（5 分钟）。
 *
 * @param id - 询价任务 ID
 * @param options - 配置选项
 * @returns TanStack Query 结果，包含询价详情
 *
 * @example
 * ```tsx
 * // 基础用法 - 自动轮询
 * const { data: quote, isLoading, error } = useQuote(123)
 *
 * // 禁用轮询
 * const { data: quote } = useQuote(123, { enablePolling: false })
 *
 * // 自定义轮询间隔
 * const { data: quote } = useQuote(123, { pollingInterval: 5000 })
 *
 * // 在详情页中使用
 * function QuoteDetailPage() {
 *   const { id } = useParams<{ id: string }>()
 *   const { data: quote, isLoading, error } = useQuote(Number(id))
 *
 *   if (isLoading) return <Loading />
 *   if (error) return <Error error={error} />
 *   if (!quote) return <NotFound />
 *
 *   return <QuoteDetail quote={quote} />
 * }
 * ```
 *
 * Requirements: 2.1 (获取详情), 4.6 (轮询), 4.7 (停止轮询)
 */
export function useQuote(id: number, options?: UseQuoteOptions) {
  const {
    enablePolling = true,
    pollingInterval = POLLING_INTERVALS.QUOTE_RUNNING,
  } = options ?? {}

  // 记录轮询开始时间，用于超时检测
  const pollingStartTime = useRef<number | null>(null)

  return useQuery<PreservationQuote>({
    queryKey: quoteQueryKey(id),
    queryFn: async () => {
      const quote = await preservationQuoteApi.get(id)

      // 如果任务正在运行且尚未记录开始时间，记录当前时间
      if (shouldPoll(quote.status) && pollingStartTime.current === null) {
        pollingStartTime.current = Date.now()
      }

      // 如果任务已完成，重置轮询开始时间
      if (isCompleted(quote.status)) {
        pollingStartTime.current = null
      }

      return quote
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
     * Requirements: 4.6 (running 时每 3 秒轮询), 4.7 (完成时停止)
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

export default useQuote
