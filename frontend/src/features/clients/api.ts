/**
 * Client Feature API
 * 当事人管理模块 API 封装 - 使用 JWT 认证
 *
 * Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.8
 */

import ky from 'ky'

import type {
  Client,
  ClientInput,
  ClientListParams,
  OcrRecognizeResult,
} from './types'
import { getAccessToken } from '@/lib/token'

/**
 * API 基础路径
 */
const API_BASE = 'http://localhost:8002/api/v1/client'

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
 * 当事人 API
 */
export const clientApi = {
  /**
   * 获取当事人列表
   * GET /api/v1/client/clients
   *
   * 注意：后端返回简单数组，前端转换为分页格式
   *
   * @param params - 查询参数（分页、搜索、筛选）
   * @returns 当事人数组
   *
   * Requirements: 9.1
   */
  list: async (params?: ClientListParams): Promise<Client[]> => {
    const searchParams = new URLSearchParams()

    if (params?.page !== undefined) {
      searchParams.set('page', String(params.page))
    }
    if (params?.page_size !== undefined) {
      searchParams.set('page_size', String(params.page_size))
    }
    if (params?.client_type) {
      searchParams.set('client_type', params.client_type)
    }
    if (params?.is_our_client !== undefined) {
      searchParams.set('is_our_client', String(params.is_our_client))
    }
    if (params?.search) {
      searchParams.set('search', params.search)
    }

    return api
      .get('clients', { searchParams })
      .json<Client[]>()
  },

  /**
   * 获取当事人详情
   * GET /api/v1/client/clients/{id}
   *
   * @param id - 当事人 ID
   * @returns 当事人详情
   *
   * Requirements: 9.2
   */
  get: async (id: number | string): Promise<Client> => {
    return api.get(`clients/${id}`).json<Client>()
  },

  /**
   * 创建当事人
   * POST /api/v1/client/clients
   *
   * @param data - 当事人信息
   * @returns 创建的当事人
   *
   * Requirements: 9.3
   */
  create: async (data: ClientInput): Promise<Client> => {
    return api.post('clients', { json: data }).json<Client>()
  },

  /**
   * 更新当事人
   * PUT /api/v1/client/clients/{id}
   *
   * @param id - 当事人 ID
   * @param data - 更新的当事人信息
   * @returns 更新后的当事人
   *
   * Requirements: 9.4
   */
  update: async (id: number | string, data: ClientInput): Promise<Client> => {
    return api.put(`clients/${id}`, { json: data }).json<Client>()
  },

  /**
   * 删除当事人
   * DELETE /api/v1/client/clients/{id}
   *
   * @param id - 当事人 ID
   * @returns void
   *
   * Requirements: 9.5
   */
  delete: async (id: number | string): Promise<void> => {
    await api.delete(`clients/${id}`)
  },

  /**
   * OCR 识别身份证
   * POST /api/v1/client/ocr/recognize-id-card
   *
   * @param file - 身份证图片文件
   * @returns OCR 识别结果
   *
   * Requirements: 6.4
   */
  recognizeIdCard: async (file: File): Promise<OcrRecognizeResult> => {
    const formData = new FormData()
    formData.append('file', file)

    const token = getAccessToken()
    const headers: Record<string, string> = {}
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }

    return ky
      .post(`${API_BASE}/ocr/recognize-id-card`, {
        body: formData,
        headers,
        // 不设置 Content-Type，让浏览器自动设置 multipart/form-data
      })
      .json<OcrRecognizeResult>()
  },

  /**
   * OCR 识别营业执照
   * POST /api/v1/client/ocr/recognize-business-license
   *
   * @param file - 营业执照图片文件
   * @returns OCR 识别结果
   *
   * Requirements: 6.5
   */
  recognizeBusinessLicense: async (file: File): Promise<OcrRecognizeResult> => {
    const formData = new FormData()
    formData.append('file', file)

    const token = getAccessToken()
    const headers: Record<string, string> = {}
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }

    return ky
      .post(`${API_BASE}/ocr/recognize-business-license`, {
        body: formData,
        headers,
        // 不设置 Content-Type，让浏览器自动设置 multipart/form-data
      })
      .json<OcrRecognizeResult>()
  },
}

export default clientApi
