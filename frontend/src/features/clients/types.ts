/**
 * Client Feature Type Definitions
 * 当事人管理模块的类型定义
 */

// ============================================================================
// 枚举类型
// ============================================================================

export type ClientType = 'natural' | 'legal' | 'non_legal_org'

export const CLIENT_TYPE_LABELS: Record<ClientType, string> = {
  natural: '自然人',
  legal: '法人',
  non_legal_org: '非法人组织',
}

export type DocType =
  | 'id_card'
  | 'passport'
  | 'hk_macao_permit'
  | 'residence_permit'
  | 'household_register'
  | 'business_license'
  | 'legal_rep_id_card'

export const DOC_TYPE_LABELS: Record<DocType, string> = {
  id_card: '身份证',
  passport: '护照',
  hk_macao_permit: '港澳通行证',
  residence_permit: '居住证',
  household_register: '户口本',
  business_license: '营业执照',
  legal_rep_id_card: '法定代表人身份证',
}

/** 自然人可用证件类型 */
export const NATURAL_DOC_TYPES: DocType[] = [
  'id_card', 'passport', 'hk_macao_permit', 'residence_permit', 'household_register',
]

/** 法人/非法人组织可用证件类型 */
export const LEGAL_DOC_TYPES: DocType[] = [
  'business_license', 'legal_rep_id_card',
  'id_card', 'passport', 'hk_macao_permit', 'residence_permit', 'household_register',
]

export type ClueType = 'bank' | 'alipay' | 'wechat' | 'real_estate' | 'other'

export const CLUE_TYPE_LABELS: Record<ClueType, string> = {
  bank: '银行账户',
  alipay: '支付宝账户',
  wechat: '微信账户',
  real_estate: '不动产',
  other: '其他',
}

// ============================================================================
// 实体类型
// ============================================================================

export interface IdentityDoc {
  doc_type: DocType
  file_path: string
  uploaded_at: string
  media_url: string | null
}

export interface IdentityDocDetail {
  id: number
  client_id: number
  doc_type: DocType
  file_path: string
  uploaded_at: string
  media_url: string | null
}

export interface Client {
  id: number
  name: string
  is_our_client: boolean
  phone: string | null
  address: string | null
  client_type: ClientType
  client_type_label: string
  id_number: string | null
  legal_representative: string | null
  legal_representative_id_number: string | null
  identity_docs: IdentityDoc[]
  created_at?: string
}

export interface ClientInput {
  name: string
  is_our_client?: boolean
  phone?: string | null
  address?: string | null
  client_type: ClientType
  id_number?: string | null
  legal_representative?: string | null
  legal_representative_id_number?: string | null
}

// ============================================================================
// 财产线索
// ============================================================================

export interface PropertyClueAttachment {
  id: number
  file_path: string
  file_name: string
  uploaded_at: string
  media_url: string | null
}

export interface PropertyClue {
  id: number
  client_id: number
  clue_type: ClueType
  clue_type_label: string
  content: string
  attachments: PropertyClueAttachment[]
  created_at: string
  updated_at: string
}

export interface PropertyClueInput {
  clue_type: ClueType
  content?: string
}

// ============================================================================
// 企业信息预填
// ============================================================================

export interface EnterpriseCompany {
  company_id: string
  company_name: string
  legal_person: string
  status: string
  establish_date: string
  registered_capital: string
  phone: string
}

export interface EnterpriseSearchResult {
  keyword: string
  provider: string
  items: EnterpriseCompany[]
  total: number
}

export interface EnterpriseProfile {
  company_id: string
  company_name: string
  unified_social_credit_code: string
  legal_person: string
  status: string
  establish_date: string
  registered_capital: string
  address: string
  business_scope: string
  phone: string
}

export interface EnterprisePrefillData {
  client_type: string
  name: string
  id_number: string
  legal_representative: string
  address: string
  phone: string
}

export interface EnterprisePrefillResult {
  provider: string
  prefill: EnterprisePrefillData
  profile: EnterpriseProfile
  existing_client: { id: number; name: string } | null
}

// ============================================================================
// 文本解析
// ============================================================================

export interface ParseTextResult {
  success: boolean
  client?: Record<string, string>
  clients?: Record<string, string>[]
  parse_method?: string
  error?: string
}

// ============================================================================
// API 请求/响应类型
// ============================================================================

export interface ClientListParams {
  page?: number
  page_size?: number
  client_type?: ClientType
  is_our_client?: boolean
  search?: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export type ClientListResponse = PaginatedResponse<Client>

export interface OcrRecognizeResult {
  success: boolean
  doc_type: string
  extracted_data: {
    name?: string
    id_number?: string
    address?: string
    legal_representative?: string
  }
  confidence: number
  error?: string
}

export interface ApiError {
  code: string
  message: string
  errors?: Record<string, string>
}

export interface OcrResult {
  name?: string
  id_number?: string
  address?: string
  legal_representative?: string
  client_type?: ClientType
}

export type ClientFormMode = 'create' | 'edit'
