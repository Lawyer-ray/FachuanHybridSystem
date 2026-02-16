/**
 * Organization Feature Type Definitions
 *
 * 组织管理模块的类型定义（律所、律师、团队、凭证）
 * Requirements: 8.1-8.18
 */

// ============================================================================
// 枚举类型
// ============================================================================

/**
 * 团队类型枚举
 */
export type TeamType = 'lawyer' | 'biz'

/**
 * 团队类型标签映射
 */
export const TEAM_TYPE_LABELS: Record<TeamType, string> = {
  lawyer: '律师团队',
  biz: '业务团队',
}

// ============================================================================
// 律所类型
// ============================================================================

/**
 * 律所输出（API 响应）
 */
export interface LawFirm {
  id: number
  name: string
  address: string
  phone: string
  social_credit_code: string
  bank_name?: string
  bank_account?: string
}

/**
 * 律所创建输入
 */
export interface LawFirmInput {
  name: string
  address?: string
  phone?: string
  social_credit_code?: string
  bank_name?: string
  bank_account?: string
}

/**
 * 律所更新输入
 */
export interface LawFirmUpdateInput {
  name?: string
  address?: string
  phone?: string
  social_credit_code?: string
  bank_name?: string
  bank_account?: string
}

// ============================================================================
// 律师类型
// ============================================================================

/**
 * 律师输出（API 响应）
 */
export interface Lawyer {
  id: number
  username: string
  real_name: string
  phone: string | null
  license_no: string
  id_card: string
  law_firm: number | null
  is_admin: boolean
  is_active: boolean
  license_pdf_url: string | null
  law_firm_detail: LawFirm | null
}

/**
 * 律师创建输入
 */
export interface LawyerCreateInput {
  username: string
  password: string
  real_name?: string
  phone?: string
  license_no?: string
  id_card?: string
  law_firm_id?: number
  is_admin?: boolean
  lawyer_team_ids?: number[]
  biz_team_ids?: number[]
}

/**
 * 律师更新输入
 */
export interface LawyerUpdateInput {
  real_name?: string
  phone?: string
  license_no?: string
  id_card?: string
  law_firm_id?: number
  is_admin?: boolean
  password?: string
  lawyer_team_ids?: number[]
  biz_team_ids?: number[]
}

// ============================================================================
// 团队类型
// ============================================================================

/**
 * 团队输出（API 响应）
 */
export interface Team {
  id: number
  name: string
  team_type: TeamType
  law_firm: number
}

/**
 * 团队创建/更新输入
 */
export interface TeamInput {
  name: string
  team_type: TeamType
  law_firm_id: number
}

// ============================================================================
// 账号凭证类型
// ============================================================================

/**
 * 凭证输出（API 响应）
 */
export interface AccountCredential {
  id: number
  lawyer: number
  site_name: string
  url: string
  account: string
  created_at: string
  updated_at: string
}

/**
 * 凭证创建输入
 */
export interface CredentialInput {
  lawyer_id: number
  site_name: string
  url?: string
  account: string
  password: string
}

/**
 * 凭证更新输入
 */
export interface CredentialUpdateInput {
  site_name?: string
  url?: string
  account?: string
  password?: string
}

// ============================================================================
// API 请求/响应类型
// ============================================================================

/**
 * 律师列表查询参数
 */
export interface LawyerListParams {
  search?: string
}

/**
 * 团队列表查询参数
 */
export interface TeamListParams {
  law_firm_id?: number
  team_type?: TeamType
}

/**
 * 凭证列表查询参数
 */
export interface CredentialListParams {
  lawyer_id?: number
  lawyer_name?: string
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
 * 表单模式
 */
export type FormMode = 'create' | 'edit'

/**
 * Tab 类型
 */
export type OrganizationTab = 'lawfirms' | 'lawyers' | 'teams' | 'credentials'

/**
 * Tab 标签映射
 */
export const ORGANIZATION_TAB_LABELS: Record<OrganizationTab, string> = {
  lawfirms: '律所',
  lawyers: '律师',
  teams: '团队',
  credentials: '凭证',
}
