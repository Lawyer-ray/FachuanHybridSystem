/**
 * Client Feature API
 * 当事人管理模块 API 封装
 */

import { createApiClient } from '@/lib/api'

import type {
  Client,
  ClientInput,
  ClientListParams,
  EnterpriseSearchResult,
  EnterprisePrefillResult,
  OcrRecognizeResult,
  ParseTextResult,
  PropertyClue,
  PropertyClueAttachment,
  PropertyClueInput,
  RelatedItems,
} from './types'

const api = createApiClient({ prefixUrl: `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002/api/v1'}/client` })

export const clientApi = {
  // ==================== 当事人 CRUD ====================

  list: async (params?: ClientListParams): Promise<Client[]> => {
    const searchParams = new URLSearchParams()
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

  createWithDocs: async (data: ClientInput, docTypes: string[], files: File[]): Promise<Client> => {
    const formData = new FormData()
    formData.append('payload', JSON.stringify(data))
    for (const dt of docTypes) formData.append('doc_types', dt)
    for (const f of files) formData.append('files', f)
    return api.post('clients-with-docs', { body: formData }).json<Client>()
  },

  checkOaCredential: async (): Promise<{ has_credential: boolean }> => {
    return api.get('clients/check-oa-credential').json()
  },

  // ==================== 文本解析 ====================

  validateIdCard: async (idNumber: string): Promise<{ valid: boolean; message: string }> => {
    return api.post('clients/validate-id-card', { json: { id_number: idNumber } }).json()
  },

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

  deleteIdentityDoc: async (docId: number): Promise<void> => {
    await api.delete(`identity-docs/${docId}`)
  },

  recognizeIdentityDoc: async (file: File, docType = 'id_card', enableOllama = false): Promise<OcrRecognizeResult> => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post('identity-doc/recognize', {
      body: formData,
      searchParams: { doc_type: docType, enable_ollama: String(enableOllama) },
    }).json<OcrRecognizeResult>()
  },

  submitRecognizeTask: async (file: File): Promise<{ task_id: string; status: string }> => {
    const formData = new FormData()
    formData.append('file', file)
    return api.post('identity-doc/recognize/submit', { body: formData }).json()
  },

  getRecognizeTaskStatus: async (taskId: string): Promise<{ task_id: string; status: string; result?: OcrRecognizeResult }> => {
    return api.get(`identity-doc/task/${taskId}`).json()
  },

  // ==================== 财产线索 ====================

  listPropertyClues: async (clientId: number): Promise<PropertyClue[]> => {
    return api.get(`clients/${clientId}/property-clues`).json<PropertyClue[]>()
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

  // ==================== 关联案件/合同 ====================

  getRelatedItems: async (clientId: number): Promise<RelatedItems> => {
    return api.get(`clients/${clientId}/related-items`).json<RelatedItems>()
  },

  // ==================== 身份证合并 ====================

  mergeIdCard: async (frontImage: File, backImage: File, clientId?: number): Promise<{ success: boolean; pdf_path?: string; doc_id?: number; error?: string }> => {
    const formData = new FormData()
    formData.append('front_image', frontImage)
    formData.append('back_image', backImage)
    if (clientId) formData.append('client_id', String(clientId))
    return api.post('identity-docs/merge-id-card', { body: formData }).json()
  },

  mergeIdCardDirect: async (frontImage: File, backImage: File, clientId?: number): Promise<{ success: boolean; pdf_path?: string; doc_id?: number; error?: string }> => {
    const formData = new FormData()
    formData.append('front_image', frontImage)
    formData.append('back_image', backImage)
    if (clientId) formData.append('client_id', String(clientId))
    return api.post('identity-docs/merge-id-card-direct', { body: formData }).json()
  },
}

export default clientApi
