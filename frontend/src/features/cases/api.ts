/**
 * Case Feature API
 * 案件管理模块 API 封装
 */

import ky from 'ky'

import type {
  Case,
  CaseAssignment,
  CaseCreateFull,
  CaseInput,
  CaseListParams,
  CaseLog,
  CaseLogAttachment,
  CaseNumber,
  CaseParty,
  CaseUpdate,
  CauseItem,
  CauseTreeNode,
  CourtItem,
  FeeCalculationRequest,
  FeeCalculationResponse,
  SupervisingAuthority,
} from './types'
import { getAccessToken } from '@/lib/token'

const API_BASE = 'http://localhost:8002/api/v1/cases/'

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

/** CaseFullOut response from POST /cases/full */
interface CaseFullOut {
  case: Case
  parties: CaseParty[]
  assignments: CaseAssignment[]
  logs: CaseLog[]
  case_numbers: CaseNumber[]
  supervising_authorities: SupervisingAuthority[]
}

export const caseApi = {
  // ==================== 案件 CRUD ====================

  list: async (params?: CaseListParams): Promise<Case[]> => {
    const searchParams = new URLSearchParams()
    if (params?.case_type) searchParams.set('case_type', params.case_type)
    if (params?.status) searchParams.set('status', params.status)
    if (params?.case_number) searchParams.set('case_number', params.case_number)
    return api.get('cases', { searchParams }).json<Case[]>()
  },

  search: async (q: string, limit = 10): Promise<Case[]> => {
    return api.get('cases/search', { searchParams: { q, limit: String(limit) } }).json<Case[]>()
  },

  get: async (id: number | string): Promise<Case> => {
    return api.get(`cases/${id}`).json<Case>()
  },

  create: async (data: CaseInput): Promise<Case> => {
    return api.post('cases', { json: data }).json<Case>()
  },

  createFull: async (data: CaseCreateFull): Promise<CaseFullOut> => {
    return api.post('cases/full', { json: data }).json<CaseFullOut>()
  },

  update: async (id: number | string, data: CaseUpdate): Promise<Case> => {
    return api.put(`cases/${id}`, { json: data }).json<Case>()
  },

  delete: async (id: number | string): Promise<void> => {
    await api.delete(`cases/${id}`)
  },

  // ==================== 当事人 ====================

  listParties: async (caseId: number | string): Promise<CaseParty[]> => {
    return api.get('parties', { searchParams: { case_id: String(caseId) } }).json<CaseParty[]>()
  },

  createParty: async (data: { case_id: number; client_id: number; legal_status?: string }): Promise<CaseParty> => {
    return api.post('parties', { json: data }).json<CaseParty>()
  },

  updateParty: async (id: number | string, data: { case_id?: number; client_id?: number; legal_status?: string }): Promise<CaseParty> => {
    return api.put(`parties/${id}`, { json: data }).json<CaseParty>()
  },

  deleteParty: async (id: number | string): Promise<void> => {
    await api.delete(`parties/${id}`)
  },

  // ==================== 指派 ====================

  listAssignments: async (caseId: number | string): Promise<CaseAssignment[]> => {
    return api.get('assignments', { searchParams: { case_id: String(caseId) } }).json<CaseAssignment[]>()
  },

  createAssignment: async (data: { case_id: number; lawyer_id: number }): Promise<CaseAssignment> => {
    return api.post('assignments', { json: data }).json<CaseAssignment>()
  },

  deleteAssignment: async (id: number | string): Promise<void> => {
    await api.delete(`assignments/${id}`)
  },

  // ==================== 日志 ====================

  listLogs: async (caseId: number | string): Promise<CaseLog[]> => {
    return api.get('logs', { searchParams: { case_id: String(caseId) } }).json<CaseLog[]>()
  },

  createLog: async (data: { case_id: number; content: string }): Promise<CaseLog> => {
    return api.post('logs', { json: data }).json<CaseLog>()
  },

  updateLog: async (id: number | string, data: { case_id?: number; content?: string }): Promise<CaseLog> => {
    return api.put(`logs/${id}`, { json: data }).json<CaseLog>()
  },

  deleteLog: async (id: number | string): Promise<void> => {
    await api.delete(`logs/${id}`)
  },

  uploadLogAttachments: async (logId: number | string, files: File[]): Promise<CaseLogAttachment[]> => {
    const formData = new FormData()
    files.forEach((file) => formData.append('files', file))
    return api.post(`logs/${logId}/attachments`, { body: formData }).json<CaseLogAttachment[]>()
  },

  // ==================== 案号 ====================

  listCaseNumbers: async (caseId: number | string): Promise<CaseNumber[]> => {
    return api.get('case-numbers', { searchParams: { case_id: String(caseId) } }).json<CaseNumber[]>()
  },

  createCaseNumber: async (data: { case_id: number; number: string; remarks?: string }): Promise<CaseNumber> => {
    return api.post('case-numbers', { json: data }).json<CaseNumber>()
  },

  updateCaseNumber: async (id: number | string, data: { number?: string; remarks?: string }): Promise<CaseNumber> => {
    return api.put(`case-numbers/${id}`, { json: data }).json<CaseNumber>()
  },

  deleteCaseNumber: async (id: number | string): Promise<void> => {
    await api.delete(`case-numbers/${id}`)
  },

  // ==================== 参考数据 ====================

  searchCauses: async (search: string, caseType?: string, limit = 50): Promise<CauseItem[]> => {
    const searchParams = new URLSearchParams({ search, limit: String(limit) })
    if (caseType) searchParams.set('case_type', caseType)
    return api.get('causes-data', { searchParams }).json<CauseItem[]>()
  },

  getCausesTree: async (parentId?: number): Promise<CauseTreeNode[]> => {
    const searchParams = new URLSearchParams()
    if (parentId !== undefined) searchParams.set('parent_id', String(parentId))
    return api.get('causes-tree', { searchParams }).json<CauseTreeNode[]>()
  },

  searchCourts: async (search: string, limit = 50): Promise<CourtItem[]> => {
    return api.get('courts-data', { searchParams: { search, limit: String(limit) } }).json<CourtItem[]>()
  },

  // ==================== 诉讼费计算 ====================

  calculateFee: async (data: FeeCalculationRequest): Promise<FeeCalculationResponse> => {
    return api.post('calculate-fee', { json: data }).json<FeeCalculationResponse>()
  },
}

export default caseApi
