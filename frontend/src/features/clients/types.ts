/**
 * Client Feature Type Definitions
 *
 * 当事人管理模块的类型定义
 * Requirements: 9.1, 9.2
 */

// ============================================================================
// 枚举类型
// ============================================================================

/**
 * 当事人类型枚举
 */
export type ClientType = 'natural' | 'legal' | 'non_legal_org'

/**
 * 当事人类型标签映射
 */
export const CLIENT_TYPE_LABELS: Record<ClientType, string> = {
  natural: '自然人',
  legal: '法人',
  non_legal_org: '非法人组织',
}

/**
 * 证件类型枚举
 */
export type DocType =
  | 'id_card' // 身份证
  | 'passport' // 护照
  | 'hk_macao_permit' // 港澳通行证
  | 'residence_permit' // 居住证
  | 'household_register' // 户口本
  | 'business_license' // 营业执照
  | 'legal_rep_id_card' // 法定代表人身份证

/**
 * 证件类型标签映射
 */
export const DOC_TYPE_LABELS: Record<DocType, string> = {
  id_card: '身份证',
  passport: '护照',
  hk_macao_permit: '港澳通行证',
  residence_permit: '居住证',
  household_register: '户口本',
  business_license: '营业执照',
  legal_rep_id_card: '法定代表人身份证',
}

// ============================================================================
// 实体类型
// ============================================================================

/**
 * 身份证件
 */
export interface IdentityDoc {
  doc_type: DocType
  file_path: string
  uploaded_at: string
  media_url: string | null
}

/**
 * 当事人输出（API 响应）
 */
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
  /** 创建时间（可选，后端可能未返回） */
  created_at?: string
}

/**
 * 当事人输入（创建/更新）
 */
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
// API 请求/响应类型
// ============================================================================

/**
 * 列表查询参数
 */
export interface ClientListParams {
  page?: number
  page_size?: number
  client_type?: ClientType
  is_our_client?: boolean
  search?: string
}

/**
 * 分页响应
 */
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

/**
 * 当事人列表响应
 */
export type ClientListResponse = PaginatedResponse<Client>

/**
 * OCR 识别结果
 */
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

/**
 * API 错误响应
 */
export interface ApiError {
  code: string
  message: string
  errors?: Record<string, string>
}

// ============================================================================
// 组件 Props 类型
// ============================================================================

/**
 * OCR 识别结果（用于表单自动填充）
 */
export interface OcrResult {
  name?: string
  id_number?: string
  address?: string
  legal_representative?: string
  client_type?: ClientType
}

/**
 * 当事人表单模式
 */
export type ClientFormMode = 'create' | 'edit'
