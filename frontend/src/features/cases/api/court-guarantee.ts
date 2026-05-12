import { createFeatureApiClient } from '@/lib/api'

const client = createFeatureApiClient('court-guarantee')

export interface QuoteItem {
  id: number
  company_name: string
  premium: string
  min_amount: string
  max_amount: string
  max_apply_amount: string
  status: string
  error_message: string
  is_recommended: boolean
}

export interface CourtGuaranteeCaseInfo {
  case_id: number
  case_name: string
  court_name: string | null
  cause_of_action: string
  preserve_amount: string | null
  preserve_category: string
  has_case_number: boolean
  has_court_credential: boolean
  our_party_is_plaintiff_side: boolean
  insurance_company_name: string
  insurance_company_options: string[]
  consultant_code: string
  quote_context: {
    binding_id: number
    quote_id: number
    status: string
    items: QuoteItem[]
  } | null
  reusable_quotes: unknown[]
  respondent_options: { party_id: number; name: string; legal_status?: string; legal_status_display?: string }[]
}

export interface QuoteEnsureRequest {
  case_id: number
  insurer_id?: string
  respondent_id?: number
  consultant_code?: string
}

export interface CourtGuaranteeQuote {
  quote_id: number
  status: string
  amount: number | null
  insurer: string | null
  premium: number | null
  error: string | null
}

export interface CourtGuaranteeSession {
  session_id: string
  status: string
  progress: number
  current_step: string
  result: Record<string, unknown> | null
  error: string | null
  timing?: {
    overall_start: number
    login_end?: number
    playwright_start?: number
    playwright_end?: number
    overall_end?: number
  } | null
}

export const courtGuaranteeApi = {
  getCaseInfo: async (caseId: number | string): Promise<CourtGuaranteeCaseInfo> =>
    client.get(`case-info/${caseId}`).json<CourtGuaranteeCaseInfo>(),

  ensureQuote: async (data: QuoteEnsureRequest): Promise<CourtGuaranteeQuote> =>
    client.post('quote/ensure', { json: data }).json<CourtGuaranteeQuote>(),

  bindQuote: async (quoteId: number): Promise<{ success: boolean }> =>
    client.post(`quote/${quoteId}/bind`, { json: {} }).json<{ success: boolean }>(),

  retryQuote: async (quoteId: number): Promise<CourtGuaranteeQuote> =>
    client.post(`quote/${quoteId}/retry`, { json: {} }).json<CourtGuaranteeQuote>(),

  deleteQuote: async (quoteId: number): Promise<{ success: boolean }> =>
    client.post(`quote/${quoteId}/delete`, { json: {} }).json<{ success: boolean }>(),

  deleteQuoteBinding: async (bindingId: number): Promise<{ success: boolean }> =>
    client.post(`quote-binding/${bindingId}/delete`, { json: {} }).json<{ success: boolean }>(),

  execute: async (caseId: number): Promise<CourtGuaranteeSession> =>
    client.post('execute', { json: { case_id: caseId } }).json<CourtGuaranteeSession>(),

  getSession: async (sessionId: string): Promise<CourtGuaranteeSession> =>
    client.get(`session/${sessionId}`).json<CourtGuaranteeSession>(),
}
