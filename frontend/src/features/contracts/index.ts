/**
 * Contract Feature Module
 */

// Types
export type {
  CaseType, ContractStatus, FeeMode, InvoiceStatus, PartyRole,
  Contract, ContractInput, ContractUpdate, ContractListParams,
  ContractPayment, PaymentInput, PaymentUpdate,
  ContractParty, ContractAssignment, ContractPartyInput,
  SupplementaryAgreement, SupplementaryAgreementInput, SupplementaryAgreementUpdate,
  FolderBinding, FolderBrowseEntry, FolderBrowseResponse,
  FolderScanStart, FolderScanStatus, FolderScanCandidate, FolderScanConfirmItem,
  FinanceStats, PaginatedResponse, Lawyer, CaseItem, Reminder,
  ContractPartySource,
} from './types'

// API
export { contractApi } from './api'

// Hooks
export { useContract, contractQueryKey } from './hooks/use-contract'
export { useContractMutations } from './hooks/use-contract-mutations'
export { useClientsSelect } from './hooks/use-clients-select'

// Components
export { ContractList } from './components/ContractList'
export { ContractDetail } from './components/ContractDetail'
export { ContractForm } from './components/ContractForm'
