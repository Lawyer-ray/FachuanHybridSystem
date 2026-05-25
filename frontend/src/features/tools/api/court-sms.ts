/**
 * Court SMS API
 * 法院短信模块 API 封装
 */

import { createFeatureApiClient, API_BASE_URL } from '@/lib/api'

export interface CourtSMSItem {
  id: number
  content: string
  received_at: string
  sms_type: string | null
  status: string
  case_name: string | null
  has_documents: boolean
  feishu_sent: boolean
  created_at: string
}

export interface CourtSMSListResponse {
  items: CourtSMSItem[]
  total: number
  page: number
  page_size: number
}

export interface CourtSMSDetail {
  id: number
  content: string
  received_at: string
  sms_type: string | null
  download_links: string[]
  case_numbers: string[]
  party_names: string[]
  status: string
  error_message: string | null
  retry_count: number
  case: { id: number; name: string } | null
  documents: {
    id: number
    name: string
    source: string
    download_url: string | null
  }[]
  feishu_sent_at: string | null
  feishu_error: string | null
  notification_results: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface CourtSMSListParams {
  page?: number
  page_size?: number
  status?: string
  sms_type?: string
  has_case?: boolean
  date_from?: string
  date_to?: string
}

const api = createFeatureApiClient('automation/court-sms')

export const courtSmsApi = {
  list: (params?: CourtSMSListParams): Promise<CourtSMSListResponse> => {
    const searchParams = new URLSearchParams()
    if (params?.page) searchParams.set('page', String(params.page))
    if (params?.page_size) searchParams.set('page_size', String(params.page_size))
    if (params?.status) searchParams.set('status', params.status)
    if (params?.sms_type) searchParams.set('sms_type', params.sms_type)
    if (params?.has_case !== undefined) searchParams.set('has_case', String(params.has_case))
    if (params?.date_from) searchParams.set('date_from', params.date_from)
    if (params?.date_to) searchParams.set('date_to', params.date_to)
    return api.get('', { searchParams }).json<CourtSMSListResponse>()
  },

  get: (id: number): Promise<CourtSMSDetail> =>
    api.get(String(id)).json<CourtSMSDetail>(),

  submit: (content: string, received_at?: string): Promise<{ success: boolean; data: { id: number; status: string; created_at: string } }> =>
    api.post('', { json: { content, received_at } }).json(),

  assignCase: (id: number, case_id: number): Promise<{ success: boolean; data: { id: number; status: string; case: { id: number; name: string } | null } }> =>
    api.post(`${id}/assign-case`, { json: { case_id } }).json(),

  retry: (id: number): Promise<{ success: boolean; data: { id: number; status: string } }> =>
    api.post(`${id}/retry`).json(),

  delete: (id: number): Promise<{ success: boolean }> =>
    api.delete(String(id)).json(),

  deleteBatch: (ids: number[]): Promise<{ deleted: number }> =>
    api.post('batch-delete', { json: { ids } }).json(),

  downloadDocumentUrl: (smsId: number, refIndex: number): string =>
    `${API_BASE_URL}/automation/court-sms/${smsId}/documents/${refIndex}/download`,

  downloadAllUrl: (smsId: number): string =>
    `${API_BASE_URL}/automation/court-sms/${smsId}/documents/download-all`,

  renameDocument: (smsId: number, refIndex: number, newStem: string): Promise<{ success: boolean; error?: string; new_name?: string }> =>
    api.post(`${smsId}/documents/${refIndex}/rename`, { json: { new_stem: newStem } }).json(),
}
