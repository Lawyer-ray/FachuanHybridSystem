import { api, createFeatureApiClient } from '@/lib/api'
import type { Contract, ContractInput, ContractUpdate, ContractListParams, ContractPartySource } from '../types'

const client = createFeatureApiClient('contracts')

export const contractsApi = {
  list: async (params?: ContractListParams): Promise<Contract[]> => {
    const sp = new URLSearchParams()
    if (params?.case_type) sp.set('case_type', params.case_type)
    if (params?.status) sp.set('status', params.status)
    if (params?.search) sp.set('search', params.search)
    if (params?.fee_mode) sp.set('fee_mode', params.fee_mode)
    if (params?.is_filed !== undefined) sp.set('is_filed', String(params.is_filed))
    return client.get('contracts', { searchParams: sp }).json<Contract[]>()
  },

  get: async (id: number | string): Promise<Contract> =>
    client.get(`contracts/${id}`).json<Contract>(),

  create: async (data: ContractInput): Promise<Contract> =>
    client.post('contracts', { json: { payload: data } }).json<Contract>(),

  createFull: async (data: ContractInput & { cases?: Record<string, unknown>[] }): Promise<Contract> =>
    client.post('contracts/full', { json: { payload: data } }).json<Contract>(),

  update: async (id: number | string, data: ContractUpdate): Promise<Contract> =>
    client.put(`contracts/${id}`, { json: { payload: data } }).json<Contract>(),

  delete: async (id: number | string): Promise<void> => {
    await api.delete(`contracts/${id}`)
  },

  updateLawyers: async (id: number | string, lawyerIds: number[]): Promise<Contract> =>
    client.put(`contracts/${id}/lawyers`, { json: { lawyer_ids: lawyerIds } }).json<Contract>(),

  getAllParties: async (id: number | string): Promise<ContractPartySource[]> =>
    client.get(`contracts/${id}/all-parties`).json<ContractPartySource[]>(),

  duplicateContract: async (contractId: number | string): Promise<Contract> =>
    client.post(`${contractId}/duplicate`).json<Contract>(),

  createCaseFromContract: async (contractId: number | string): Promise<{ case_id: number; message: string }> =>
    client.post(`${contractId}/create-case`).json(),

  renewAdvisorContract: async (contractId: number | string, data: { start_date: string; end_date: string }): Promise<Contract> =>
    client.post(`${contractId}/renew`, { json: data }).json<Contract>(),
}
