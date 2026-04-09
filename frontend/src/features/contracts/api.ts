/**
 * Contract Feature API
 */

import { api } from '@/lib/api'
import type {
  Contract, ContractInput, ContractUpdate, ContractListParams,
  ContractPayment, PaymentInput, PaymentUpdate,
  SupplementaryAgreement, SupplementaryAgreementInput, SupplementaryAgreementUpdate,
  FolderBinding, FolderBrowseResponse,
  FolderScanStart, FolderScanSubfolderList, FolderScanStatus,
  FolderScanConfirmItem, FolderScanConfirmResult,
  FinanceStats, PaginatedResponse, ContractPartySource,
} from './types'

const contractApi_ = api.extend({
  prefixUrl: 'http://localhost:8002/api/v1/contracts',
})

export const contractApi = {
  // ==================== Contract CRUD ====================

  list: async (params?: ContractListParams): Promise<Contract[]> => {
    const sp = new URLSearchParams()
    if (params?.case_type) sp.set('case_type', params.case_type)
    if (params?.status) sp.set('status', params.status)
    return contractApi_.get('contracts', { searchParams: sp }).json<Contract[]>()
  },

  get: async (id: number | string): Promise<Contract> =>
    contractApi_.get(`contracts/${id}`).json<Contract>(),

  create: async (data: ContractInput): Promise<Contract> =>
    contractApi_.post('contracts', { json: data }).json<Contract>(),

  createFull: async (data: ContractInput & { cases?: Record<string, unknown>[] }): Promise<Contract> =>
    contractApi_.post('contracts/full', { json: data }).json<Contract>(),

  update: async (id: number | string, data: ContractUpdate): Promise<Contract> =>
    contractApi_.put(`contracts/${id}`, { json: data }).json<Contract>(),

  delete: async (id: number | string): Promise<void> => {
    await api.delete(`contracts/${id}`)
  },

  updateLawyers: async (id: number | string, lawyerIds: number[]): Promise<Contract> =>
    contractApi_.put(`contracts/${id}/lawyers`, { json: { lawyer_ids: lawyerIds } }).json<Contract>(),

  getAllParties: async (id: number | string): Promise<ContractPartySource[]> =>
    contractApi_.get(`contracts/${id}/all-parties`).json<ContractPartySource[]>(),

  // ==================== Payments ====================

  listPayments: async (params?: { contract_id?: number; invoice_status?: string; start_date?: string; end_date?: string }): Promise<ContractPayment[]> => {
    const sp = new URLSearchParams()
    if (params?.contract_id !== undefined) sp.set('contract_id', String(params.contract_id))
    if (params?.invoice_status) sp.set('invoice_status', params.invoice_status)
    if (params?.start_date) sp.set('start_date', params.start_date)
    if (params?.end_date) sp.set('end_date', params.end_date)
    return contractApi_.get('finance/payments', { searchParams: sp }).json<ContractPayment[]>()
  },

  createPayment: async (data: PaymentInput): Promise<ContractPayment> =>
    contractApi_.post('finance/payments', { json: data }).json<ContractPayment>(),

  updatePayment: async (id: number, data: PaymentUpdate): Promise<ContractPayment> =>
    contractApi_.put(`finance/payments/${id}`, { json: data }).json<ContractPayment>(),

  deletePayment: async (id: number, confirm = false): Promise<void> => {
    await api.delete(`finance/payments/${id}`, { searchParams: confirm ? { confirm: 'true' } : {} })
  },

  getFinanceStats: async (params?: { contract_id?: number; start_date?: string; end_date?: string }): Promise<FinanceStats> => {
    const sp = new URLSearchParams()
    if (params?.contract_id !== undefined) sp.set('contract_id', String(params.contract_id))
    if (params?.start_date) sp.set('start_date', params.start_date)
    if (params?.end_date) sp.set('end_date', params.end_date)
    return contractApi_.get('finance/stats', { searchParams: sp }).json<FinanceStats>()
  },

  // ==================== Supplementary Agreements ====================

  listAgreements: async (contractId: number): Promise<SupplementaryAgreement[]> =>
    contractApi_.get(`contracts/${contractId}/supplementary-agreements`).json<SupplementaryAgreement[]>(),

  getAgreement: async (id: number): Promise<SupplementaryAgreement> =>
    contractApi_.get(`supplementary-agreements/${id}`).json<SupplementaryAgreement>(),

  createAgreement: async (data: SupplementaryAgreementInput): Promise<SupplementaryAgreement> =>
    contractApi_.post('supplementary-agreements', { json: data }).json<SupplementaryAgreement>(),

  updateAgreement: async (id: number, data: SupplementaryAgreementUpdate): Promise<SupplementaryAgreement> =>
    contractApi_.put(`supplementary-agreements/${id}`, { json: data }).json<SupplementaryAgreement>(),

  deleteAgreement: async (id: number): Promise<void> => {
    await api.delete(`supplementary-agreements/${id}`)
  },

  // ==================== Folder Binding ====================

  getBinding: async (contractId: number): Promise<FolderBinding | null> =>
    contractApi_.get(`${contractId}/folder-binding`).json<FolderBinding | null>(),

  createBinding: async (contractId: number, folderPath: string): Promise<FolderBinding> =>
    contractApi_.post(`${contractId}/folder-binding`, { json: { folder_path: folderPath } }).json<FolderBinding>(),

  deleteBinding: async (contractId: number): Promise<{ success: boolean; message: string }> =>
    contractApi_.delete(`${contractId}/folder-binding`).json(),

  browseFolders: async (path?: string, includeHidden = false): Promise<FolderBrowseResponse> => {
    const sp = new URLSearchParams()
    if (path) sp.set('path', path)
    if (includeHidden) sp.set('include_hidden', 'true')
    return contractApi_.get('folder-browse', { searchParams: sp }).json<FolderBrowseResponse>()
  },

  // ==================== Folder Scan ====================

  startScan: async (contractId: number, rescan = false, scanSubfolder = ''): Promise<FolderScanStart> =>
    contractApi_.post(`${contractId}/folder-scan`, { json: { rescan, scan_subfolder: scanSubfolder } }).json<FolderScanStart>(),

  listScanSubfolders: async (contractId: number): Promise<FolderScanSubfolderList> =>
    contractApi_.get(`${contractId}/folder-scan/subfolders`).json<FolderScanSubfolderList>(),

  getScanStatus: async (contractId: number, sessionId: string): Promise<FolderScanStatus> =>
    contractApi_.get(`${contractId}/folder-scan/${sessionId}`).json<FolderScanStatus>(),

  confirmScan: async (contractId: number, sessionId: string, items: FolderScanConfirmItem[]): Promise<FolderScanConfirmResult> =>
    contractApi_.post(`${contractId}/folder-scan/${sessionId}/confirm`, { json: { items } }).json<FolderScanConfirmResult>(),
}

export default contractApi
