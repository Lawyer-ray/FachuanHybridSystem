import { createFeatureApiClient } from '@/lib/api'

const client = createFeatureApiClient('court-filing')

export interface CourtFilingCaseInfo {
  case_id: number
  case_name: string
  cause_of_action: string | null
  court_name: string | null
  target_amount: string | null
  plaintiff_name: string | null
  defendant_name: string | null
  our_party_is_plaintiff_side: boolean
  has_court_credential: boolean
  has_http_plugin: boolean
  suggested_filing_type: string | null
  default_filing_engine: string
  material_slots: { slot_name: string; matched_file: string | null; required: boolean }[]
}

export interface CourtFilingExecuteRequest {
  case_id: number
  filing_type?: 'civil' | 'execution' | null
  filing_engine?: 'api' | 'playwright' | null
}

export interface CourtFilingSession {
  success: boolean
  message: string
  session_id: number | null
  status: string | null
  timing?: {
    overall_start: number
    login_end?: number
    http_start?: number
    http_end?: number
    playwright_start?: number
    playwright_end?: number
    overall_end?: number
  } | null
}

export const courtFilingApi = {
  getCaseInfo: async (caseId: number | string): Promise<CourtFilingCaseInfo> =>
    client.get(`case-info/${caseId}`).json<CourtFilingCaseInfo>(),

  execute: async (data: CourtFilingExecuteRequest): Promise<CourtFilingSession> =>
    client.post('execute', { json: data }).json<CourtFilingSession>(),

  getSession: async (sessionId: string): Promise<CourtFilingSession> =>
    client.get(`session/${sessionId}`).json<CourtFilingSession>(),
}
