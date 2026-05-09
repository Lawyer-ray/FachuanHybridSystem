import { api, createFeatureApiClient } from '@/lib/api'
import type { ContractPayment, PaymentInput, PaymentUpdate, FinanceStats } from '../types'

const client = createFeatureApiClient('contracts')

export const paymentsApi = {
  list: async (params?: { contract_id?: number; invoice_status?: string; start_date?: string; end_date?: string }): Promise<ContractPayment[]> => {
    const sp = new URLSearchParams()
    if (params?.contract_id !== undefined) sp.set('contract_id', String(params.contract_id))
    if (params?.invoice_status) sp.set('invoice_status', params.invoice_status)
    if (params?.start_date) sp.set('start_date', params.start_date)
    if (params?.end_date) sp.set('end_date', params.end_date)
    return client.get('finance/payments', { searchParams: sp }).json<ContractPayment[]>()
  },

  create: async (data: PaymentInput): Promise<ContractPayment> =>
    client.post('finance/payments', { json: data }).json<ContractPayment>(),

  update: async (id: number, data: PaymentUpdate): Promise<ContractPayment> =>
    client.put(`finance/payments/${id}`, { json: data }).json<ContractPayment>(),

  delete: async (id: number, confirm = false): Promise<void> => {
    await api.delete(`finance/payments/${id}`, { searchParams: confirm ? { confirm: 'true' } : {} })
  },

  getFinanceStats: async (params?: { contract_id?: number; start_date?: string; end_date?: string }): Promise<FinanceStats> => {
    const sp = new URLSearchParams()
    if (params?.contract_id !== undefined) sp.set('contract_id', String(params.contract_id))
    if (params?.start_date) sp.set('start_date', params.start_date)
    if (params?.end_date) sp.set('end_date', params.end_date)
    return client.get('finance/stats', { searchParams: sp }).json<FinanceStats>()
  },
}
