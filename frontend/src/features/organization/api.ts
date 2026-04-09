/**
 * Organization Feature API
 * 组织管理模块 API 封装 - 使用 JWT 认证
 *
 * 包含：律所、律师、团队、凭证的 CRUD 操作
 * Requirements: 8.1-8.21
 */

import ky from 'ky'

import type {
  LawFirm,
  LawFirmInput,
  LawFirmUpdateInput,
  Lawyer,
  LawyerCreateInput,
  LawyerUpdateInput,
  LawyerListParams,
  Team,
  TeamInput,
  TeamListParams,
  AccountCredential,
  CredentialInput,
  CredentialUpdateInput,
  CredentialListParams,
} from './types'
import { getAccessToken } from '@/lib/token'

/**
 * API 基础路径
 */
const API_BASE = 'http://localhost:8002/api/v1/organization'

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

// ============================================================================
// 律所 API
// Requirements: 8.1-8.5
// ============================================================================

/**
 * 律所 API
 */
export const lawFirmApi = {
  /**
   * 获取律所列表
   * GET /api/v1/organization/lawfirms
   *
   * @returns 律所数组
   *
   * Requirements: 8.1
   */
  list: async (): Promise<LawFirm[]> => {
    return api.get('lawfirms').json<LawFirm[]>()
  },

  /**
   * 获取律所详情
   * GET /api/v1/organization/lawfirms/{id}
   *
   * @param id - 律所 ID
   * @returns 律所详情
   *
   * Requirements: 8.2
   */
  get: async (id: number | string): Promise<LawFirm> => {
    return api.get(`lawfirms/${id}`).json<LawFirm>()
  },

  /**
   * 创建律所
   * POST /api/v1/organization/lawfirms
   *
   * @param data - 律所信息
   * @returns 创建的律所
   *
   * Requirements: 8.3
   */
  create: async (data: LawFirmInput): Promise<LawFirm> => {
    return api.post('lawfirms', { json: data }).json<LawFirm>()
  },

  /**
   * 更新律所
   * PUT /api/v1/organization/lawfirms/{id}
   *
   * @param id - 律所 ID
   * @param data - 更新的律所信息
   * @returns 更新后的律所
   *
   * Requirements: 8.4
   */
  update: async (id: number | string, data: LawFirmUpdateInput): Promise<LawFirm> => {
    return api.put(`lawfirms/${id}`, { json: data }).json<LawFirm>()
  },

  /**
   * 删除律所
   * DELETE /api/v1/organization/lawfirms/{id}
   *
   * @param id - 律所 ID
   * @returns void
   *
   * Requirements: 8.5
   */
  delete: async (id: number | string): Promise<void> => {
    await api.delete(`lawfirms/${id}`)
  },
}

// ============================================================================
// 律师 API
// Requirements: 8.6-8.10
// ============================================================================

/**
 * 律师 API
 */
export const lawyerApi = {
  /**
   * 获取律师列表
   * GET /api/v1/organization/lawyers
   *
   * @param params - 查询参数（搜索）
   * @returns 律师数组
   *
   * Requirements: 8.6
   */
  list: async (params?: LawyerListParams): Promise<Lawyer[]> => {
    const searchParams = new URLSearchParams()

    if (params?.search) {
      searchParams.set('search', params.search)
    }

    return api
      .get('lawyers', { searchParams })
      .json<Lawyer[]>()
  },

  /**
   * 获取律师详情
   * GET /api/v1/organization/lawyers/{id}
   *
   * @param id - 律师 ID
   * @returns 律师详情
   *
   * Requirements: 8.7
   */
  get: async (id: number | string): Promise<Lawyer> => {
    return api.get(`lawyers/${id}`).json<Lawyer>()
  },

  /**
   * 创建律师
   * POST /api/v1/organization/lawyers
   *
   * 支持文件上传（执业证 PDF）
   *
   * @param data - 律师信息
   * @param licensePdf - 执业证 PDF 文件（可选）
   * @returns 创建的律师
   *
   * Requirements: 8.8
   */
  create: async (data: LawyerCreateInput, licensePdf?: File): Promise<Lawyer> => {
    if (licensePdf) {
      // 使用 FormData 上传文件
      const formData = new FormData()

      // 添加 JSON 数据字段
      Object.entries(data).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          if (Array.isArray(value)) {
            // 数组字段需要特殊处理
            value.forEach((item) => {
              formData.append(key, String(item))
            })
          } else {
            formData.append(key, String(value))
          }
        }
      })

      // 添加文件
      formData.append('license_pdf', licensePdf)

      const token = getAccessToken()
      const headers: Record<string, string> = {}
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      return ky
        .post(`${API_BASE}/lawyers`, {
          body: formData,
          headers,
          // 不设置 Content-Type，让浏览器自动设置 multipart/form-data
        })
        .json<Lawyer>()
    }

    // 无文件时使用 JSON
    return api.post('lawyers', { json: data }).json<Lawyer>()
  },

  /**
   * 更新律师
   * PUT /api/v1/organization/lawyers/{id}
   *
   * 支持文件上传（执业证 PDF）
   *
   * @param id - 律师 ID
   * @param data - 更新的律师信息
   * @param licensePdf - 执业证 PDF 文件（可选）
   * @returns 更新后的律师
   *
   * Requirements: 8.9
   */
  update: async (
    id: number | string,
    data: LawyerUpdateInput,
    licensePdf?: File
  ): Promise<Lawyer> => {
    if (licensePdf) {
      // 使用 FormData 上传文件
      const formData = new FormData()

      // 添加 JSON 数据字段
      Object.entries(data).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
          if (Array.isArray(value)) {
            // 数组字段需要特殊处理
            value.forEach((item) => {
              formData.append(key, String(item))
            })
          } else {
            formData.append(key, String(value))
          }
        }
      })

      // 添加文件
      formData.append('license_pdf', licensePdf)

      const token = getAccessToken()
      const headers: Record<string, string> = {}
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }

      return ky
        .put(`${API_BASE}/lawyers/${id}`, {
          body: formData,
          headers,
          // 不设置 Content-Type，让浏览器自动设置 multipart/form-data
        })
        .json<Lawyer>()
    }

    // 无文件时使用 JSON
    return api.put(`lawyers/${id}`, { json: data }).json<Lawyer>()
  },

  /**
   * 删除律师
   * DELETE /api/v1/organization/lawyers/{id}
   *
   * @param id - 律师 ID
   * @returns void
   *
   * Requirements: 8.10
   */
  delete: async (id: number | string): Promise<void> => {
    await api.delete(`lawyers/${id}`)
  },
}

// ============================================================================
// 团队 API
// Requirements: 8.11-8.14
// ============================================================================

/**
 * 团队 API
 */
export const teamApi = {
  /**
   * 获取团队列表
   * GET /api/v1/organization/teams
   *
   * @param params - 查询参数（律所 ID、团队类型）
   * @returns 团队数组
   *
   * Requirements: 8.11
   */
  list: async (params?: TeamListParams): Promise<Team[]> => {
    const searchParams = new URLSearchParams()

    if (params?.law_firm_id !== undefined) {
      searchParams.set('law_firm_id', String(params.law_firm_id))
    }
    if (params?.team_type) {
      searchParams.set('team_type', params.team_type)
    }

    return api
      .get('teams', { searchParams })
      .json<Team[]>()
  },

  /**
   * 获取团队详情
   * GET /api/v1/organization/teams/{id}
   *
   * @param id - 团队 ID
   * @returns 团队详情
   *
   * Requirements: 8.11 (扩展)
   */
  get: async (id: number | string): Promise<Team> => {
    return api.get(`teams/${id}`).json<Team>()
  },

  /**
   * 创建团队
   * POST /api/v1/organization/teams
   *
   * @param data - 团队信息
   * @returns 创建的团队
   *
   * Requirements: 8.12
   */
  create: async (data: TeamInput): Promise<Team> => {
    return api.post('teams', { json: data }).json<Team>()
  },

  /**
   * 更新团队
   * PUT /api/v1/organization/teams/{id}
   *
   * @param id - 团队 ID
   * @param data - 更新的团队信息
   * @returns 更新后的团队
   *
   * Requirements: 8.13
   */
  update: async (id: number | string, data: TeamInput): Promise<Team> => {
    return api.put(`teams/${id}`, { json: data }).json<Team>()
  },

  /**
   * 删除团队
   * DELETE /api/v1/organization/teams/{id}
   *
   * @param id - 团队 ID
   * @returns void
   *
   * Requirements: 8.14
   */
  delete: async (id: number | string): Promise<void> => {
    await api.delete(`teams/${id}`)
  },
}

// ============================================================================
// 凭证 API
// Requirements: 8.15-8.18
// ============================================================================

/**
 * 凭证 API
 */
export const credentialApi = {
  /**
   * 获取凭证列表
   * GET /api/v1/organization/credentials
   *
   * @param params - 查询参数（律师 ID、律师姓名）
   * @returns 凭证数组
   *
   * Requirements: 8.15
   */
  list: async (params?: CredentialListParams): Promise<AccountCredential[]> => {
    const searchParams = new URLSearchParams()

    if (params?.lawyer_id !== undefined) {
      searchParams.set('lawyer_id', String(params.lawyer_id))
    }
    if (params?.lawyer_name) {
      searchParams.set('lawyer_name', params.lawyer_name)
    }

    return api
      .get('credentials', { searchParams })
      .json<AccountCredential[]>()
  },

  /**
   * 获取凭证详情
   * GET /api/v1/organization/credentials/{id}
   *
   * @param id - 凭证 ID
   * @returns 凭证详情
   *
   * Requirements: 8.15 (扩展)
   */
  get: async (id: number | string): Promise<AccountCredential> => {
    return api.get(`credentials/${id}`).json<AccountCredential>()
  },

  /**
   * 创建凭证
   * POST /api/v1/organization/credentials
   *
   * @param data - 凭证信息
   * @returns 创建的凭证
   *
   * Requirements: 8.16
   */
  create: async (data: CredentialInput): Promise<AccountCredential> => {
    return api.post('credentials', { json: data }).json<AccountCredential>()
  },

  /**
   * 更新凭证
   * PUT /api/v1/organization/credentials/{id}
   *
   * @param id - 凭证 ID
   * @param data - 更新的凭证信息
   * @returns 更新后的凭证
   *
   * Requirements: 8.17
   */
  update: async (
    id: number | string,
    data: CredentialUpdateInput
  ): Promise<AccountCredential> => {
    return api.put(`credentials/${id}`, { json: data }).json<AccountCredential>()
  },

  /**
   * 删除凭证
   * DELETE /api/v1/organization/credentials/{id}
   *
   * @param id - 凭证 ID
   * @returns void
   *
   * Requirements: 8.18
   */
  delete: async (id: number | string): Promise<void> => {
    await api.delete(`credentials/${id}`)
  },
}

// ============================================================================
// 默认导出
// ============================================================================

export default {
  lawFirm: lawFirmApi,
  lawyer: lawyerApi,
  team: teamApi,
  credential: credentialApi,
}
