import { createFeatureApiClient } from '@/lib/api'

const client = createFeatureApiClient('court-filing')

export interface CourtFilingCaseInfo {
  case_id: number
  case_name: string
  court_name: string | null
  filing_type: string | null
  filing_type_display: string | null
  suggested_filing_type: string | null
  filing_engine: string | null
  parties: { name: string; role: string; id_number: string | null }[]
  has_credentials: boolean
  material_slots: { slot_name: string; matched_file: string | null; required: boolean }[]
}

export interface CourtFilingExecuteRequest {
  case_id: number
  filing_type: 'civil' | 'execution'
  engine?: 'api' | 'playwright'
}

export interface CourtFilingSession {
  session_id: string
  status: string
  progress: number
  current_step: string
  result: Record<string, unknown> | null
  error: string | null
}

export const courtFilingApi = {
  getCaseInfo: async (caseId: number | string): Promise<CourtFilingCaseInfo> =>
    client.get(`case-info/${caseId}`).json<CourtFilingCaseInfo>(),

  execute: async (data: CourtFilingExecuteRequest): Promise<CourtFilingSession> =>
    client.post('execute', { json: data }).json<CourtFilingSession>(),

  getSession: async (sessionId: string): Promise<CourtFilingSession> =>
    client.get(`session/${sessionId}`).json<CourtFilingSession>(),
}
