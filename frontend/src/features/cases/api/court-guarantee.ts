import { createFeatureApiClient } from '@/lib/api'

const client = createFeatureApiClient('court-guarantee')

export interface CourtGuaranteeCaseInfo {
  case_id: number
  case_name: string
  court_name: string | null
  preservation_amount: number | null
  category: string | null
  insurance_options: { id: string; name: string }[]
  respondent_options: { id: number; name: string }[]
  quote_context: {
    quote_id: number | null
    status: string | null
    amount: number | null
    insurer: string | null
    premium: number | null
    binding_id: number | null
  } | null
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
