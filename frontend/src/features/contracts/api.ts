/**
 * Contract Feature API
 */

import { api, API_BASE_URL } from '@/lib/api'
import type {
  Contract, ContractInput, ContractUpdate, ContractListParams,
  ContractPayment, PaymentInput, PaymentUpdate,
  SupplementaryAgreement, SupplementaryAgreementInput, SupplementaryAgreementUpdate,
  FolderBinding, FolderBrowseResponse,
  FolderScanStart, FolderScanSubfolderList, FolderScanStatus,
  FolderScanConfirmItem, FolderScanConfirmResult,
  FinanceStats, ContractPartySource,
  Invoice, ClientPaymentRecord,
  OAConfig, FilingSession, ArchiveChecklist,
} from './types'

const contractApi_ = api.extend({
  prefixUrl: `${API_BASE_URL}/contracts`,
})

export const contractApi = {
  // ==================== Contract CRUD ====================

  list: async (params?: ContractListParams): Promise<Contract[]> => {
    const sp = new URLSearchParams()
    if (params?.case_type) sp.set('case_type', params.case_type)
    if (params?.status) sp.set('status', params.status)
    if (params?.search) sp.set('search', params.search)
    if (params?.fee_mode) sp.set('fee_mode', params.fee_mode)
    if (params?.is_filed !== undefined) sp.set('is_filed', String(params.is_filed))
    return contractApi_.get('contracts', { searchParams: sp }).json<Contract[]>()
  },

  get: async (id: number | string): Promise<Contract> =>
    contractApi_.get(`contracts/${id}`).json<Contract>(),

  create: async (data: ContractInput): Promise<Contract> =>
    contractApi_.post('contracts', { json: { payload: data } }).json<Contract>(),

  createFull: async (data: ContractInput & { cases?: Record<string, unknown>[] }): Promise<Contract> =>
    contractApi_.post('contracts/full', { json: { payload: data } }).json<Contract>(),

  update: async (id: number | string, data: ContractUpdate): Promise<Contract> =>
    contractApi_.put(`contracts/${id}`, { json: { payload: data } }).json<Contract>(),

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

  // ==================== Archive Operations ====================

  getArchiveChecklist: async (contractId: number | string): Promise<ArchiveChecklist> =>
    contractApi_.get(`${contractId}/archive/checklist`).json<ArchiveChecklist>(),

  generateArchiveFolder: async (contractId: number | string): Promise<{ success: boolean; generated_docs: string[]; archive_dir: string; errors: string[] }> =>
    contractApi_.post(`${contractId}/archive/generate-folder`).json(),

  syncCaseMaterials: async (contractId: number | string): Promise<{ synced_count: number; message: string }> =>
    contractApi_.post(`${contractId}/archive/sync-case-materials`).json(),

  resetAndResyncCaseMaterials: async (contractId: number | string): Promise<{ synced_count: number; message: string }> =>
    contractApi_.post(`${contractId}/archive/reset-and-resync`).json(),

  scaleToA4: async (contractId: number | string): Promise<{ scaled_count: number; message: string }> =>
    contractApi_.post(`${contractId}/archive/scale-to-a4`).json(),

  toggleCompactArchive: async (contractId: number | string): Promise<{ compact: boolean }> =>
    contractApi_.post(`${contractId}/archive/toggle-compact`).json(),

  confirmArchive: async (contractId: number | string): Promise<{ success: boolean; message: string }> =>
    contractApi_.post(`${contractId}/archive/confirm`).json(),

  uploadArchiveItem: async (contractId: number | string, file: File, category: string): Promise<{ id: number; filename: string }> => {
    const form = new FormData()
    form.append('file', file)
    form.append('category', category)
    return contractApi_.post(`${contractId}/archive/upload`, { body: form }).json()
  },

  deleteArchiveMaterial: async (contractId: number | string, materialId: number): Promise<void> => {
    await contractApi_.delete(`${contractId}/archive/materials/${materialId}`)
  },

  reorderArchiveMaterials: async (contractId: number | string, orders: Record<string, number[]>): Promise<void> => {
    await contractApi_.post(`${contractId}/archive/reorder`, { json: { orders } })
  },

  moveArchiveMaterial: async (contractId: number | string, materialId: number, targetCode: string): Promise<void> => {
    await contractApi_.post(`${contractId}/archive/materials/${materialId}/move`, { json: { target_code: targetCode } })
  },

  clearAllArchiveMaterials: async (contractId: number | string): Promise<{ deleted_count: number }> =>
    contractApi_.post(`${contractId}/archive/clear-all`).json(),

  previewArchiveMaterial: async (contractId: number | string, materialId: number): Promise<Response> =>
    contractApi_.get(`${contractId}/archive/materials/${materialId}/preview`),

  // ==================== Document Generation ====================

  generateContract: async (contractId: number | string, splitFee = false): Promise<Response> =>
    api.get(`documents/contracts/${contractId}/download`, { searchParams: splitFee ? { split_fee: 'true' } : {} }),

  generateFolder: async (contractId: number | string): Promise<Blob> =>
    api.get(`documents/contracts/${contractId}/folder/download`).blob(),

  generateSupplementaryAgreement: async (contractId: number | string, agreementId: number): Promise<Response> =>
    api.get(`documents/contracts/${contractId}/supplementary-agreements/${agreementId}/download`),

  // ==================== Contract Actions ====================

  duplicateContract: async (contractId: number | string): Promise<Contract> =>
    contractApi_.post(`${contractId}/duplicate`).json<Contract>(),

  createCaseFromContract: async (contractId: number | string): Promise<{ case_id: number; message: string }> =>
    contractApi_.post(`${contractId}/create-case`).json(),

  renewAdvisorContract: async (contractId: number | string, data: { start_date: string; end_date: string }): Promise<Contract> =>
    contractApi_.post(`${contractId}/renew`, { json: data }).json<Contract>(),

  // ==================== Invoice CRUD ====================

  listInvoices: async (contractId: number | string): Promise<Invoice[]> =>
    contractApi_.get(`${contractId}/invoices`).json<Invoice[]>(),

  createInvoice: async (contractId: number | string, data: { amount: number; invoice_no?: string; issued_at?: string; note?: string }): Promise<Invoice> =>
    contractApi_.post(`${contractId}/invoices`, { json: data }).json<Invoice>(),

  deleteInvoice: async (contractId: number | string, invoiceId: number): Promise<void> => {
    await contractApi_.delete(`${contractId}/invoices/${invoiceId}`)
  },

  // ==================== Client Payment Records ====================

  listClientPaymentRecords: async (contractId: number | string): Promise<ClientPaymentRecord[]> =>
    contractApi_.get(`${contractId}/client-payment-records`).json<ClientPaymentRecord[]>(),

  createClientPaymentRecord: async (contractId: number | string, data: FormData): Promise<ClientPaymentRecord> =>
    contractApi_.post(`${contractId}/client-payment-records`, { body: data }).json<ClientPaymentRecord>(),

  deleteClientPaymentRecord: async (contractId: number | string, recordId: number): Promise<void> => {
    await contractApi_.delete(`${contractId}/client-payment-records/${recordId}`)
  },

  // ==================== OA Filing ====================

  fetchOAConfigs: async (): Promise<OAConfig[]> =>
    api.get('oa-filing/configs').json<OAConfig[]>(),

  executeOAFiling: async (siteName: string, contractId: number, caseId?: number): Promise<FilingSession> =>
    api.post('oa-filing/execute', { json: { site_name: siteName, contract_id: contractId, case_id: caseId ?? null } }).json<FilingSession>(),

  getFilingSession: async (sessionId: number): Promise<FilingSession> =>
    api.get(`oa-filing/session/${sessionId}`).json<FilingSession>(),
}

export default contractApi
