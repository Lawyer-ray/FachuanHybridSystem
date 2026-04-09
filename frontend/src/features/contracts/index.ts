/**
 * Contract Feature Module
 */

// Types
export type {
  CaseType, CaseStatus, FeeMode, InvoiceStatus, PartyRole,
  Contract, ContractInput, ContractUpdate, ContractListParams,
  ContractPayment, PaymentInput, PaymentUpdate,
  ContractParty, ContractAssignment, ContractPartyInput,
  SupplementaryAgreement, SupplementaryAgreementInput, SupplementaryAgreementUpdate,
  FolderBinding, FolderBrowseEntry, FolderBrowseResponse,
  FolderScanStart, FolderScanStatus, FolderScanCandidate, FolderScanConfirmItem,
  FinanceStats, PaginatedResponse, Lawyer, CaseItem, Reminder,
  ContractPartySource,
} from './types'

export {
  CASE_TYPE_LABELS, CASE_STATUS_LABELS, FEE_MODE_LABELS,
  INVOICE_STATUS_LABELS, PARTY_ROLE_LABELS,
} from './types'

// API
export { contractApi } from './api'
export { default as contractApiDefault } from './api'

// Hooks
export { useContracts, contractsQueryKey } from './hooks/use-contracts'
export { useContract, contractQueryKey } from './hooks/use-contract'
export { useContractMutations } from './hooks/use-contract-mutations'
export { useLawyers } from './hooks/use-lawyers'
export { useClientsSelect } from './hooks/use-clients-select'

// Hooks - Payments & Agreements
export { usePayments } from './hooks/use-payments'
export { usePaymentMutations } from './hooks/use-payment-mutations'
export { useAgreementMutations } from './hooks/use-agreement-mutations'

// Hooks - Folder
export { useFolderBinding, useFolderBrowse } from './hooks/use-folder-binding'
export { useFolderScan, useScanStatus } from './hooks/use-folder-scan'

// Components
export { ContractList } from './components/ContractList'
export { ContractTable } from './components/ContractTable'
export { ContractFilters } from './components/ContractFilters'
export { ContractDetail } from './components/ContractDetail'
export { ContractInfoCard } from './components/ContractInfoCard'
export { ContractForm } from './components/ContractForm'
export { PaymentList } from './components/PaymentList'
export { PaymentFormDialog } from './components/PaymentFormDialog'
export { SupplementaryAgreementList } from './components/SupplementaryAgreementList'
export { AgreementFormDialog } from './components/AgreementFormDialog'
export { FolderBindingManager } from './components/FolderBindingManager'
export { FolderBrowser } from './components/FolderBrowser'
export { FolderScanPanel } from './components/FolderScanPanel'
