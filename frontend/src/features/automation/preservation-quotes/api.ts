/**
 * Preservation Quotes API
 * 财产保全询价模块 API 封装 - 使用 JWT 认证
 *
 * Requirements: 2.1, 3.6, 4.5, 4.9
 */

import ky from 'ky'

import type {
  PaginatedResponse,
  PreservationQuote,
  PreservationQuoteCreate,
  QuoteListParams,
} from './types'
import { getAccessToken } from '@/lib/token'

/**
 * API 基础路径
 */
const API_BASE = 'http://localhost:8002/api/v1/automation/preservation-quotes'

/**
 * 创建带 JWT 认证的 Ky 实例
 */
const api = ky.create({
  prefixUrl: API_BASE,
  hooks: {
    beforeRequest: [
      (request) => {
        const token = getAccessToken()
        if (token) {
          request.headers.set('Authorization', `Bearer ${token}`)
        }
      },
    ],
  },
})

/**
 * 财产保全询价 API
 */
export const preservationQuoteApi = {
  /**
   * 获取询价任务列表
   * GET /api/v1/automation/preservation-quotes/
   *
   * @param params - 查询参数（分页、状态筛选）
   * @returns 分页的询价任务列表
   *
   * Requirements: 2.1
   */
  list: async (
    params?: QuoteListParams
  ): Promise<PaginatedResponse<PreservationQuote>> => {
    const searchParams = new URLSearchParams()

    if (params?.page !== undefined) {
      searchParams.set('page', String(params.page))
    }
    if (params?.page_size !== undefined) {
      searchParams.set('page_size', String(params.page_size))
    }
    if (params?.status !== undefined) {
      searchParams.set('status', params.status)
    }

    return api.get('', { searchParams }).json<PaginatedResponse<PreservationQuote>>()
  },

  /**
   * 获取询价任务详情
   * GET /api/v1/automation/preservation-quotes/{id}/
   *
   * @param id - 询价任务 ID
   * @returns 询价任务详情（包含保险报价列表）
   *
   * Requirements: 4.1
   */
  get: async (id: number): Promise<PreservationQuote> => {
    return api.get(`${id}/`).json<PreservationQuote>()
  },

  /**
   * 创建询价任务
   * POST /api/v1/automation/preservation-quotes/
   *
   * @param data - 创建询价请求数据
   * @returns 创建的询价任务
   *
   * Requirements: 3.6
   */
  create: async (data: PreservationQuoteCreate): Promise<PreservationQuote> => {
    return api.post('', { json: data }).json<PreservationQuote>()
  },

  /**
   * 执行询价任务
   * POST /api/v1/automation/preservation-quotes/{id}/execute/
   *
   * @param id - 询价任务 ID
   * @returns 更新后的询价任务（状态变为 running）
   *
   * Requirements: 4.5
   */
  execute: async (id: number): Promise<PreservationQuote> => {
    return api.post(`${id}/execute/`).json<PreservationQuote>()
  },

  /**
   * 重试询价任务
   * POST /api/v1/automation/preservation-quotes/{id}/retry/
   *
   * @param id - 询价任务 ID
   * @returns 更新后的询价任务（状态变为 running）
   *
   * Requirements: 4.9
   */
  retry: async (id: number): Promise<PreservationQuote> => {
    return api.post(`${id}/retry/`).json<PreservationQuote>()
  },
}

export default preservationQuoteApi
