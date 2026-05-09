import { createFeatureApiClient } from '@/lib/api'
import type { CaseParty, CaseAssignment, CaseAccessGrant } from '../types'

const client = createFeatureApiClient('cases')

export const partiesApi = {
  list: async (caseId: number | string): Promise<CaseParty[]> =>
    client.get('parties', { searchParams: { case_id: String(caseId) } }).json<CaseParty[]>(),

  create: async (data: { case_id: number; client_id: number; legal_status?: string }): Promise<CaseParty> =>
    client.post('parties', { json: data }).json<CaseParty>(),

  update: async (id: number | string, data: { case_id?: number; client_id?: number; legal_status?: string }): Promise<CaseParty> =>
    client.put(`parties/${id}`, { json: data }).json<CaseParty>(),

  delete: async (id: number | string): Promise<void> => {
    await client.delete(`parties/${id}`)
  },

  listAssignments: async (caseId: number | string): Promise<CaseAssignment[]> =>
    client.get('assignments', { searchParams: { case_id: String(caseId) } }).json<CaseAssignment[]>(),

  createAssignment: async (data: { case_id: number; lawyer_id: number }): Promise<CaseAssignment> =>
    client.post('assignments', { json: data }).json<CaseAssignment>(),

  deleteAssignment: async (id: number | string): Promise<void> => {
    await client.delete(`assignments/${id}`)
  },

  listGrants: async (caseId: number | string): Promise<CaseAccessGrant[]> =>
    client.get('grants', { searchParams: { case_id: String(caseId) } }).json<CaseAccessGrant[]>(),

  createGrant: async (data: { case_id: number; grantee_id: number }): Promise<CaseAccessGrant> =>
    client.post('grants', { json: data }).json<CaseAccessGrant>(),

  deleteGrant: async (id: number | string): Promise<void> => {
    await client.delete(`grants/${id}`)
  },
}
