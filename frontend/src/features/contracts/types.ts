/**
 * Contract Feature Type Definitions
 */

// ============================================================================
// Enums
// ============================================================================

export type CaseType = 'civil' | 'criminal' | 'administrative' | 'labor' | 'intl' | 'special' | 'advisor'

export const CASE_TYPE_LABELS: Record<CaseType, string> = {
  civil: '民商事', criminal: '刑事', administrative: '行政',
  labor: '劳动仲裁', intl: '商事仲裁', special: '专项服务', advisor: '常法顾问',
}

export type CaseStatus = 'active' | 'closed'

export const CASE_STATUS_LABELS: Record<CaseStatus, string> = {
  active: '在办', closed: '已结案',
}

export type FeeMode = 'FIXED' | 'SEMI_RISK' | 'FULL_RISK' | 'CUSTOM'

export const FEE_MODE_LABELS: Record<FeeMode, string> = {
  FIXED: '固定收费', SEMI_RISK: '半风险收费', FULL_RISK: '全风险收费', CUSTOM: '自定义',
}

export type InvoiceStatus = 'UNINVOICED' | 'INVOICED_PARTIAL' | 'INVOICED_FULL'

export const INVOICE_STATUS_LABELS: Record<InvoiceStatus, string> = {
  UNINVOICED: '未开票', INVOICED_PARTIAL: '部分开票', INVOICED_FULL: '已开票',
}

export type PartyRole = 'PRINCIPAL' | 'BENEFICIARY' | 'OPPOSING'

export const PARTY_ROLE_LABELS: Record<PartyRole, string> = {
  PRINCIPAL: '委托人', BENEFICIARY: '受益人', OPPOSING: '对方当事人',
}

// ============================================================================
// Entity Types
// ============================================================================

export interface Lawyer {
  id: number
  username: string
  real_name: string | null
  phone: string | null
  is_admin: boolean | null
  is_active: boolean | null
  law_firm: number | null
  law_firm_name: string | null
}

export interface CaseItem {
  id: number
  name: string
  status: string | null
  status_label: string | null
  case_type: string | null
  start_date: string | null
  effective_date: string | null
  target_amount: number | null
  preservation_amount: number | null
  cause_of_action: string | null
  current_stage: string | null
  current_stage_label: string | null
}

export interface ClientOut {
  id: number
  name: string
  is_our_client: boolean
  client_type: string
  client_type_label: string
}

export interface ContractParty {
  id: number
  contract: number
  client: number
  role: PartyRole
  client_detail: ClientOut
  role_label: string
}

export interface ContractAssignment {
  id: number
  lawyer_id: number
  lawyer_name: string
  is_primary: boolean
  order: number
}

export interface Reminder {
  id: number
  title: string
  due_date: string | null
  status: string
}

export interface ContractPayment {
  id: number
  contract: number
  amount: number
  received_at: string | null
  invoice_status: InvoiceStatus
  invoice_status_label: string
  invoiced_amount: number
  note: string | null
  created_at: string | null
  updated_at: string | null
}

export interface SupplementaryAgreementParty {
  id: number
  client: number
  role: PartyRole
  client_detail: ClientOut
  client_name: string
  is_our_client: boolean
  role_label: string
}

export interface SupplementaryAgreement {
  id: number
  contract: number
  name: string | null
  parties: SupplementaryAgreementParty[]
  created_at: string
  updated_at: string
}

export interface Contract {
  id: number
  name: string
  case_type: CaseType
  status: CaseStatus
  specified_date: string | null
  start_date: string | null
  end_date: string | null
  is_archived: boolean
  fee_mode: string
  fixed_amount: number | null
  risk_rate: number | null
  custom_terms: string | null
  representation_stages: string[]
  cases: CaseItem[]
  contract_parties: ContractParty[]
  case_type_label: string | null
  status_label: string | null
  reminders: Reminder[]
  payments: ContractPayment[]
  supplementary_agreements: SupplementaryAgreement[]
  total_received: number
  total_invoiced: number
  unpaid_amount: number | null
  assignments: ContractAssignment[]
  primary_lawyer: Lawyer | null
  matched_document_template: string | null
  matched_folder_templates: string | null
  has_matched_templates: boolean
}

// ============================================================================
// Input Types
// ============================================================================

export interface ContractPartyInput {
  client_id: number
  role: PartyRole
}

export interface ContractInput {
  name: string
  case_type: CaseType
  status?: CaseStatus
  specified_date?: string | null
  start_date?: string | null
  end_date?: string | null
  is_archived?: boolean
  fee_mode?: FeeMode
  fixed_amount?: number | null
  risk_rate?: number | null
  custom_terms?: string | null
  representation_stages?: string[]
  lawyer_ids: number[]
  parties?: ContractPartyInput[]
}

export interface ContractUpdate {
  name?: string
  case_type?: string
  status?: string
  specified_date?: string | null
  start_date?: string | null
  end_date?: string | null
  is_archived?: boolean
  fee_mode?: string
  fixed_amount?: number | null
  risk_rate?: number | null
  custom_terms?: string | null
  representation_stages?: string[]
  parties?: ContractPartyInput[]
}

export interface PaymentInput {
  contract_id: number
  amount: number
  received_at?: string | null
  invoice_status?: InvoiceStatus
  invoiced_amount?: number
  note?: string | null
  confirm?: boolean
}

export interface PaymentUpdate {
  amount?: number
  received_at?: string | null
  invoice_status?: InvoiceStatus
  invoiced_amount?: number
  note?: string | null
  confirm?: boolean
}

export interface SupplementaryAgreementInput {
  contract_id: number
  name?: string
  party_ids?: number[]
}

export interface SupplementaryAgreementUpdate {
  name?: string
  party_ids?: number[]
}

// ============================================================================
// Folder Binding
// ============================================================================

export interface FolderBinding {
  id: number
  contract_id: number
  folder_path: string
  folder_path_display: string
  created_at: string
  updated_at: string
  is_accessible: boolean
}

export interface FolderBrowseEntry {
  name: string
  path: string
}

export interface FolderBrowseResponse {
  browsable: boolean
  message: string | null
  path: string | null
  parent_path: string | null
  entries: FolderBrowseEntry[]
}

// ============================================================================
// Folder Scan
// ============================================================================

export interface FolderScanStart {
  session_id: string
  status: string
  task_id: string
}

export interface FolderScanSubfolder {
  relative_path: string
  display_name: string
}

export interface FolderScanSubfolderList {
  root_path: string
  subfolders: FolderScanSubfolder[]
}

export interface FolderScanCandidate {
  source_path: string
  filename: string
  file_size: number
  modified_at: string
  base_name: string
  version_token: string
  extract_method: string
  text_excerpt: string
  suggested_category: string
  confidence: number
  reason: string
  selected: boolean
}

export interface FolderScanStatus {
  session_id: string
  status: string
  progress: number
  current_file: string
  summary: { total_files: number; deduped_files: number; classified_files: number }
  candidates: FolderScanCandidate[]
  error_message: string
}

export interface FolderScanConfirmItem {
  source_path: string
  selected: boolean
  category: string
}

export interface FolderScanConfirmResult {
  session_id: string
  status: string
  imported_count: number
}

// ============================================================================
// Finance Stats
// ============================================================================

export interface FinanceStatsItem {
  contract_id: number
  total_received: number
  total_invoiced: number
  unpaid_amount: number | null
}

export interface FinanceStats {
  items: FinanceStatsItem[]
  total_received_all: number
  total_invoiced_all: number
}

// ============================================================================
// Pagination
// ============================================================================

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface ContractListParams {
  page?: number
  page_size?: number
  case_type?: CaseType
  status?: CaseStatus
}

export interface ContractPartySource {
  id: number
  name: string
  source: string
  role: string | null
}
