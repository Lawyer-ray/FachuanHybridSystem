/**
 * Document Recognition API
 * 文书智能识别模块 API 封装 - 使用 JWT 认证
 *
 * Requirements: 5.1, 6.5, 7.6, 7.8, 7.9
 */

import ky from 'ky'

import type {
  CaseSearchResult,
  DocumentRecognitionTask,
  ManualBindingRequest,
  RecognitionListParams,
  UpdateRecognitionInfoRequest,
} from './types'
import { getAccessToken } from '@/lib/token'

/**
 * 分页响应类型
 */
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

/**
 * API 基础路径
 */
const API_BASE = 'http://localhost:8002/api/v1/automation/document-recognition'

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
 * 文书智能识别 API
 */
export const documentRecognitionApi = {
  /**
   * 获取识别任务列表
   * GET /api/v1/automation/document-recognition/
   *
   * @param params - 查询参数（分页、状态筛选）
   * @returns 分页的识别任务列表
   *
   * Requirements: 5.1
   */
  list: async (
    params?: RecognitionListParams
  ): Promise<PaginatedResponse<DocumentRecognitionTask>> => {
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

    return api
      .get('', { searchParams })
      .json<PaginatedResponse<DocumentRecognitionTask>>()
  },

  /**
   * 获取识别任务详情
   * GET /api/v1/automation/document-recognition/{id}/
   *
   * @param id - 识别任务 ID
   * @returns 识别任务详情
   *
   * Requirements: 7.1
   */
  getTask: async (id: number): Promise<DocumentRecognitionTask> => {
    return api.get(`${id}/`).json<DocumentRecognitionTask>()
  },

  /**
   * 上传文件进行识别
   * POST /api/v1/automation/document-recognition/upload/
   *
   * @param file - 要上传的文件（PDF 或图片）
   * @returns 创建的识别任务
   *
   * Requirements: 6.5
   */
  upload: async (file: File): Promise<DocumentRecognitionTask> => {
    const formData = new FormData()
    formData.append('file', file)

    return api
      .post('upload/', {
        body: formData,
      })
      .json<DocumentRecognitionTask>()
  },

  /**
   * 搜索案件
   * GET /api/v1/automation/document-recognition/search-cases/?q={query}
   *
   * @param query - 搜索关键词
   * @returns 匹配的案件列表
   *
   * Requirements: 7.6
   */
  searchCases: async (query: string): Promise<CaseSearchResult[]> => {
    const searchParams = new URLSearchParams()
    searchParams.set('q', query)

    return api
      .get('search-cases/', { searchParams })
      .json<CaseSearchResult[]>()
  },

  /**
   * 手动绑定案件
   * POST /api/v1/automation/document-recognition/{id}/bind/
   *
   * @param id - 识别任务 ID
   * @param data - 绑定请求数据
   * @returns 更新后的识别任务
   *
   * Requirements: 7.8
   */
  bind: async (
    id: number,
    data: ManualBindingRequest
  ): Promise<DocumentRecognitionTask> => {
    return api
      .post(`${id}/bind/`, { json: data })
      .json<DocumentRecognitionTask>()
  },

  /**
   * 更新识别信息
   * PATCH /api/v1/automation/document-recognition/{id}/
   *
   * @param id - 识别任务 ID
   * @param data - 更新请求数据
   * @returns 更新后的识别任务
   *
   * Requirements: 7.9
   */
  updateInfo: async (
    id: number,
    data: UpdateRecognitionInfoRequest
  ): Promise<DocumentRecognitionTask> => {
    return api.patch(`${id}/`, { json: data }).json<DocumentRecognitionTask>()
  },
}

export default documentRecognitionApi
