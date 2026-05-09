import { contractsApi } from './contracts'
import { paymentsApi } from './payments'
import { agreementsApi } from './agreements'
import { archiveApi } from './archive'
import { foldersApi } from './folders'
import { documentsApi } from './documents'
import { invoicesApi } from './invoices'
import { oaApi } from './oa'

export const contractApi = {
  ...contractsApi,
  // Payments
  listPayments: paymentsApi.list,
  createPayment: paymentsApi.create,
  updatePayment: paymentsApi.update,
  deletePayment: paymentsApi.delete,
  getFinanceStats: paymentsApi.getFinanceStats,
  // Agreements
  listAgreements: agreementsApi.list,
  getAgreement: agreementsApi.get,
  createAgreement: agreementsApi.create,
  updateAgreement: agreementsApi.update,
  deleteAgreement: agreementsApi.delete,
  // Folders
  getBinding: foldersApi.getBinding,
  createBinding: foldersApi.createBinding,
  deleteBinding: foldersApi.deleteBinding,
  browseFolders: foldersApi.browse,
  startScan: foldersApi.startScan,
  listScanSubfolders: foldersApi.listScanSubfolders,
  getScanStatus: foldersApi.getScanStatus,
  confirmScan: foldersApi.confirmScan,
  // Archive
  getArchiveChecklist: archiveApi.getChecklist,
  generateArchiveFolder: archiveApi.generateFolder,
  learnArchiveRules: archiveApi.learnRules,
  syncCaseMaterials: archiveApi.syncCaseMaterials,
  resetAndResyncCaseMaterials: archiveApi.resetAndResync,
  scaleToA4: archiveApi.scaleToA4,
  toggleCompactArchive: archiveApi.toggleCompact,
  confirmArchive: archiveApi.confirm,
  uploadArchiveItem: archiveApi.uploadItem,
  deleteArchiveMaterial: archiveApi.deleteMaterial,
  reorderArchiveMaterials: archiveApi.reorderMaterials,
  moveArchiveMaterial: archiveApi.moveMaterial,
  clearAllArchiveMaterials: archiveApi.clearAllMaterials,
  previewArchiveMaterial: archiveApi.previewMaterial,
  downloadArchiveItem: archiveApi.downloadItem,
  previewArchiveItem: archiveApi.previewItem,
  previewSingleMaterial: archiveApi.previewSingleMaterial,
  // Documents
  previewArchivePlaceholders: documentsApi.previewArchivePlaceholders,
  generateContract: documentsApi.generateContract,
  generateFolder: documentsApi.generateFolder,
  generateSupplementaryAgreement: documentsApi.generateSupplementaryAgreement,
  // Invoices
  listInvoices: invoicesApi.list,
  createInvoice: invoicesApi.create,
  deleteInvoice: invoicesApi.delete,
  listClientPaymentRecords: invoicesApi.listClientPaymentRecords,
  createClientPaymentRecord: invoicesApi.createClientPaymentRecord,
  deleteClientPaymentRecord: invoicesApi.deleteClientPaymentRecord,
  // OA Filing
  fetchOAConfigs: oaApi.fetchConfigs,
  executeOAFiling: oaApi.execute,
  getFilingSession: oaApi.getSession,
}

export default contractApi
