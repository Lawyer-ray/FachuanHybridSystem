import ky from 'ky'
import { API_BASE_URL } from '@/lib/api'
import { api } from '@/lib/api'

import type { ProvidersListResponse, TokenExchangeResponse } from './types'

export const socialAuthApi = {
  getProviders: async (): Promise<ProvidersListResponse> => {
    return api.get('social/providers').json<ProvidersListResponse>()
  },

  tokenExchange: async (code: string): Promise<TokenExchangeResponse> => {
    return ky
      .post(`${API_BASE_URL}/social/token-exchange`, {
        json: { code },
      })
      .json<TokenExchangeResponse>()
  },
}
