/**
 * Tools API — Express Query + LPR
 */

import { createFeatureApiClient } from '@/lib/api'

// ==================== Express Query ====================

export interface ExpressQueryTask {
  id: number
  title: string
  status: string
  carrier_type: string
  tracking_number: string
  result_pdf: string | null
  created_at: string
  updated_at: string
}

const expressApi = createFeatureApiClient('express-query')

export const expressQueryApi = {
  list: (): Promise<ExpressQueryTask[]> =>
    expressApi.get('tasks').json<ExpressQueryTask[]>(),
}

// ==================== LPR ====================

export interface LPRRate {
  id: number
  effective_date: string
  rate_1y: string
  rate_5y: string
  source: string
  is_auto_synced: boolean
}

interface LPRRateListResponse {
  items: LPRRate[]
  total: number
}

const lprApi = createFeatureApiClient('lpr')

// ---- Calculate ----

export interface PrincipalChange {
  start_date: string
  end_date: string
  principal: string
}

export interface LprCalculateRequest {
  start_date?: string | null
  end_date?: string | null
  principal?: string | null
  rate_mode?: 'lpr' | 'custom'
  rate_type?: '1y' | '5y'
  multiplier?: string
  custom_rate_unit?: 'percent' | 'permille' | 'permyriad'
  custom_rate_value?: string | null
  year_days?: number
  date_inclusion?: 'both' | 'start_only' | 'end_only' | 'neither'
  principal_changes?: PrincipalChange[] | null
}

export interface CalculationPeriod {
  start_date: string
  end_date: string
  principal: string
  rate: string
  rate_unit: string | null
  days: number
  year_days: number
  interest: string
}

export interface LprCalculateResponse {
  success: boolean
  total_interest: string | null
  total_principal: string | null
  total_days: number | null
  start_date: string | null
  end_date: string | null
  periods: CalculationPeriod[] | null
  message: string | null
  code: string | null
  sync_info: string | null
}

export const lprApi_ = {
  listRates: (limit = 12): Promise<LPRRateListResponse> =>
    lprApi.get('rates', { searchParams: { limit: String(limit) } }).json<LPRRateListResponse>(),

  calculate: (body: LprCalculateRequest): Promise<LprCalculateResponse> =>
    lprApi.post('calculate', { json: body }).json<LprCalculateResponse>(),
}
