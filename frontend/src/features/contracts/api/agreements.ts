import { api, createFeatureApiClient } from '@/lib/api'
import type { SupplementaryAgreement, SupplementaryAgreementInput, SupplementaryAgreementUpdate } from '../types'

const client = createFeatureApiClient('contracts')

export const agreementsApi = {
  list: async (contractId: number): Promise<SupplementaryAgreement[]> =>
    client.get(`contracts/${contractId}/supplementary-agreements`).json<SupplementaryAgreement[]>(),

  get: async (id: number): Promise<SupplementaryAgreement> =>
    client.get(`supplementary-agreements/${id}`).json<SupplementaryAgreement>(),

  create: async (data: SupplementaryAgreementInput): Promise<SupplementaryAgreement> =>
    client.post('supplementary-agreements', { json: data }).json<SupplementaryAgreement>(),

  update: async (id: number, data: SupplementaryAgreementUpdate): Promise<SupplementaryAgreement> =>
    client.put(`supplementary-agreements/${id}`, { json: data }).json<SupplementaryAgreement>(),

  delete: async (id: number): Promise<void> => {
    await api.delete(`supplementary-agreements/${id}`)
  },
}
