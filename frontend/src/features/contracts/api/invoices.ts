import { createFeatureApiClient } from '@/lib/api'
import type { Invoice, ClientPaymentRecord } from '../types'

const client = createFeatureApiClient('contracts')

export const invoicesApi = {
  list: async (contractId: number | string): Promise<Invoice[]> =>
    client.get(`${contractId}/invoices`).json<Invoice[]>(),

  create: async (contractId: number | string, data: { amount: number; invoice_no?: string; issued_at?: string; note?: string }): Promise<Invoice> =>
    client.post(`${contractId}/invoices`, { json: data }).json<Invoice>(),

  delete: async (contractId: number | string, invoiceId: number): Promise<void> => {
    await client.delete(`${contractId}/invoices/${invoiceId}`)
  },

  listClientPaymentRecords: async (contractId: number | string): Promise<ClientPaymentRecord[]> =>
    client.get(`${contractId}/client-payment-records`).json<ClientPaymentRecord[]>(),

  createClientPaymentRecord: async (contractId: number | string, data: FormData): Promise<ClientPaymentRecord> =>
    client.post(`${contractId}/client-payment-records`, { body: data }).json<ClientPaymentRecord>(),

  deleteClientPaymentRecord: async (contractId: number | string, recordId: number): Promise<void> => {
    await client.delete(`${contractId}/client-payment-records/${recordId}`)
  },
}
