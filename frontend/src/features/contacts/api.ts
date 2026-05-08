/**
 * Contacts Feature API
 * 工作人员联系方式 API 封装
 */

import { createFeatureApiClient } from '@/lib/api'

import type { CaseContact, CaseContactInput, CaseContactSearchResult } from './types'

const api = createFeatureApiClient('contacts')

export const contactApi = {
  list: async (caseId: number | string, stage?: string): Promise<CaseContact[]> => {
    const searchParams = new URLSearchParams({ case_id: String(caseId) })
    if (stage) searchParams.set('stage', stage)
    return api.get('contacts', { searchParams }).json<CaseContact[]>()
  },

  create: async (data: CaseContactInput): Promise<CaseContact> => {
    return api.post('contacts', { json: data }).json<CaseContact>()
  },

  update: async (id: number | string, data: Partial<CaseContactInput>): Promise<CaseContact> => {
    return api.put(`contacts/${id}`, { json: data }).json<CaseContact>()
  },

  delete: async (id: number | string): Promise<void> => {
    await api.delete(`contacts/${id}`)
  },

  search: async (params: {
    q?: string
    court?: string
    role?: string
    limit?: number
  }): Promise<CaseContactSearchResult[]> => {
    const searchParams = new URLSearchParams()
    if (params.q) searchParams.set('q', params.q)
    if (params.court) searchParams.set('court', params.court)
    if (params.role) searchParams.set('role', params.role)
    if (params.limit) searchParams.set('limit', String(params.limit))
    return api.get('contacts/search', { searchParams }).json<CaseContactSearchResult[]>()
  },
}
