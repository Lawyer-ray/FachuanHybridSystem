import { createFeatureApiClient } from '@/lib/api'
import type {
  Case, CaseInput, CaseUpdate, CaseListParams, CaseCreateFull,
  CaseParty, CaseAssignment,
  CauseItem, CauseTreeNode, CourtItem,
  FeeCalculationRequest, FeeCalculationResponse,
  SupervisingAuthority, CaseLog, CaseNumber,
} from '../types'

const client = createFeatureApiClient('cases')

interface CaseFullOut {
  case: Case
  parties: CaseParty[]
  assignments: CaseAssignment[]
  logs: CaseLog[]
  case_numbers: CaseNumber[]
  supervising_authorities: SupervisingAuthority[]
}

export const casesCrudApi = {
  list: async (params?: CaseListParams): Promise<Case[]> => {
    const searchParams = new URLSearchParams()
    if (params?.case_type) searchParams.set('case_type', params.case_type)
    if (params?.status) searchParams.set('status', params.status)
    return client.get('cases', { searchParams }).json<Case[]>()
  },

  search: async (q: string, limit = 10): Promise<Case[]> =>
    client.get('cases/search', { searchParams: { q, limit: String(limit) } }).json<Case[]>(),

  get: async (id: number | string): Promise<Case> =>
    client.get(`cases/${id}`).json<Case>(),

  create: async (data: CaseInput): Promise<Case> =>
    client.post('cases', { json: data }).json<Case>(),

  createFull: async (data: CaseCreateFull): Promise<CaseFullOut> =>
    client.post('cases/full', { json: data }).json<CaseFullOut>(),

  update: async (id: number | string, data: CaseUpdate): Promise<Case> =>
    client.put(`cases/${id}`, { json: data }).json<Case>(),

  delete: async (id: number | string): Promise<void> => {
    await client.delete(`cases/${id}`)
  },

  searchCauses: async (search: string, caseType?: string, limit = 50): Promise<CauseItem[]> => {
    const searchParams = new URLSearchParams({ search, limit: String(limit) })
    if (caseType) searchParams.set('case_type', caseType)
    return client.get('causes-data', { searchParams }).json<CauseItem[]>()
  },

  getCausesTree: async (parentId?: number): Promise<CauseTreeNode[]> => {
    const searchParams = new URLSearchParams()
    if (parentId !== undefined) searchParams.set('parent_id', String(parentId))
    return client.get('causes-tree', { searchParams }).json<CauseTreeNode[]>()
  },

  searchCourts: async (search: string, limit = 50): Promise<CourtItem[]> =>
    client.get('courts-data', { searchParams: { search, limit: String(limit) } }).json<CourtItem[]>(),

  calculateFee: async (data: FeeCalculationRequest): Promise<FeeCalculationResponse> =>
    client.post('calculate-fee', { json: data }).json<FeeCalculationResponse>(),
}
