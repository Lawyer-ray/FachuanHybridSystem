/**
 * Reminder Feature API
 * 重要日期提醒模块 API 封装 - 使用 JWT 认证
 *
 * Requirements: 1.1, 4.2, 5.2, 6.2
 */

import ky from 'ky'

import type {
  Reminder,
  ReminderInput,
  ReminderTypeOption,
} from './types'
import { getAccessToken } from '@/lib/token'

/**
 * API 基础路径
 */
const API_BASE = 'http://localhost:8002/api/v1'

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
 * 列表查询参数
 */
interface ReminderListParams {
  /** 按合同 ID 筛选 */
  contract_id?: number
  /** 按案件日志 ID 筛选 */
  case_log_id?: number
}

/**
 * 提醒 API
 */
export const reminderApi = {
  /**
   * 获取提醒列表
   * GET /api/v1/reminders/list
   *
   * @param params - 查询参数（可选）
   * @returns 提醒数组
   *
   * Requirements: 1.1
   */
  list: async (params?: ReminderListParams): Promise<Reminder[]> => {
    const searchParams = new URLSearchParams()

    if (params?.contract_id !== undefined) {
      searchParams.set('contract_id', String(params.contract_id))
    }
    if (params?.case_log_id !== undefined) {
      searchParams.set('case_log_id', String(params.case_log_id))
    }

    return api
      .get('reminders/list', { searchParams })
      .json<Reminder[]>()
  },

  /**
   * 获取提醒详情
   * GET /api/v1/reminders/{id}
   *
   * @param id - 提醒 ID
   * @returns 提醒详情
   *
   * Requirements: 1.1
   */
  get: async (id: number): Promise<Reminder> => {
    return api.get(`reminders/${id}`).json<Reminder>()
  },

  /**
   * 创建提醒
   * POST /api/v1/reminders/create
   *
   * @param data - 提醒信息
   * @returns 创建的提醒
   *
   * Requirements: 4.2
   */
  create: async (data: ReminderInput): Promise<Reminder> => {
    return api.post('reminders/create', { json: data }).json<Reminder>()
  },

  /**
   * 更新提醒
   * PUT /api/v1/reminders/{id}
   *
   * @param id - 提醒 ID
   * @param data - 更新的提醒信息
   * @returns 更新后的提醒
   *
   * Requirements: 5.2
   */
  update: async (id: number, data: ReminderInput): Promise<Reminder> => {
    return api.put(`reminders/${id}`, { json: data }).json<Reminder>()
  },

  /**
   * 删除提醒
   * DELETE /api/v1/reminders/{id}
   *
   * @param id - 提醒 ID
   * @returns void
   *
   * Requirements: 6.2
   */
  delete: async (id: number): Promise<void> => {
    await api.delete(`reminders/${id}`)
  },

  /**
   * 获取提醒类型列表
   * GET /api/v1/reminders/types
   *
   * @returns 提醒类型选项数组
   *
   * Requirements: 1.1
   */
  getTypes: async (): Promise<ReminderTypeOption[]> => {
    return api.get('reminders/types').json<ReminderTypeOption[]>()
  },
}

export default reminderApi
