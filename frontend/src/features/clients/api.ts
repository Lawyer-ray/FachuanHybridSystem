/**
 * Client Feature API
 * 当事人管理模块 API 封装
 */

import ky from 'ky'

import type {
  Client,
  ClientInput,
  ClientListParams,
  EnterpriseSearchResult,
  EnterprisePrefillResult,
  IdentityDocDetail,
  OcrRecognizeResult,
  ParseTextResult,
  PropertyClue,
  PropertyClueAttachment,
  PropertyClueInput,
} from './types'
import { getAccessToken } from '@/lib/token'

const API_BASE = 'http://localhost:8002/api/v1/client'

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

export const clientApi = {
  // ==================== 当事人 CRUD ====================

  list: async (params?: ClientListParams): Promise<Client[]> => {
    const searchParams = new URLSearchParams()
    if (params?.page !== undefined) searchParams.set('page', String(params.page))
    if (params?.page_size !== undefined) searchParams.set('page_size', String(params.page_size))
    if (params?.client_type) searchParams.set('client_type', params.client_type)
    if (params?.is_our_client !== undefined) searchParams.set('is_our_client', String(params.is_our_client))
    if (params?.search) searchParams.set('search', params.search)
    return api.get('clients', { searchParams }).json<Client[]>()
  },

  get: async (id: number | string): Promise<Client> => {
    return api.get(`clients/${id}`).json<Client>()
  },

  create: async (data: ClientInput): Promise<Client> => {
    return api.post('clients', { json: data }).json<Client>()
  },

  update: async (id: number | string, data: ClientInput): Promise<Client> => {
    return api.put(`clients/${id}`, { json: data }).json<Client>()
  },

  delete: async (id: number | string): Promise<void> => {
    await api.delete(`clients/${id}`)
  },

  // ==================== 文本解析 ====================

  parseText: async (text: string, parseMultiple = false): Promise<ParseTextResult> => {
    return api.post('clients/parse-text', {
      json: { text, parse_multiple: parseMultiple },
    }).json<ParseTextResult>()
  },

  // ==================== 企业信息预填 ====================

  searchEnterprise: async (keyword: string, provider?: string, limit = 8): Promise<EnterpriseSearchResult> => {
    const searchParams = new URLSearchParams({ keyword, limit: String(limit) })
    if (provider) searchParams.set('provider', provider)
    return api.get('clients/enterprise/search', { searchParams }).json<EnterpriseSearchResult>()
  },

  getEnterprisePrefill: async (companyId: string, provider?: string): Promise<EnterprisePrefillResult> => {
    const searchParams = new URLSearchParams({ company_id: companyId })
    if (provider) searchParams.set('provider', provider)
    return api.get('clients/enterprise/prefill', { searchParams }).json<EnterprisePrefillResult>()
  },

  // ==================== 证件管理 ====================

  addIdentityDoc: async (clientId: number, docType: string, file: File): Promise<{ success: boolean; doc_id: number }> => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post(`clients/${clientId}/identity-docs`, {
      body: formData,
      searchParams: { doc_type: docType },
    }).json()
  },

  getIdentityDoc: async (docId: number): Promise<IdentityDocDetail> => {
    return api.get(`identity-docs/${docId}`).json<IdentityDocDetail>()
  },

  deleteIdentityDoc: async (docId: number): Promise<void> => {
    await api.delete(`identity-docs/${docId}`)
  },

  recognizeIdentityDoc: async (file: File, docType = 'id_card'): Promise<OcrRecognizeResult> => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post('identity-doc/recognize', {
      body: formData,
      searchParams: { doc_type: docType },
    }).json<OcrRecognizeResult>()
  },

  // ==================== 财产线索 ====================

  listPropertyClues: async (clientId: number): Promise<PropertyClue[]> => {
    return api.get(`clients/${clientId}/property-clues`).json<PropertyClue[]>()
  },

  getPropertyClue: async (clueId: number): Promise<PropertyClue> => {
    return api.get(`property-clues/${clueId}`).json<PropertyClue>()
  },

  createPropertyClue: async (clientId: number, data: PropertyClueInput): Promise<PropertyClue> => {
    return api.post(`clients/${clientId}/property-clues`, { json: data }).json<PropertyClue>()
  },

  updatePropertyClue: async (clueId: number, data: Partial<PropertyClueInput>): Promise<PropertyClue> => {
    return api.put(`property-clues/${clueId}`, { json: data }).json<PropertyClue>()
  },

  deletePropertyClue: async (clueId: number): Promise<void> => {
    await api.delete(`property-clues/${clueId}`)
  },

  getContentTemplate: async (clueType: string): Promise<{ clue_type: string; template: string }> => {
    return api.get('property-clues/content-template', {
      searchParams: { clue_type: clueType },
    }).json()
  },

  uploadClueAttachment: async (clueId: number, file: File): Promise<PropertyClueAttachment> => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post(`property-clues/${clueId}/attachments`, { body: formData }).json<PropertyClueAttachment>()
  },

  deleteClueAttachment: async (attachmentId: number): Promise<void> => {
    await api.delete(`property-clue-attachments/${attachmentId}`)
  },
}

export default clientApi
