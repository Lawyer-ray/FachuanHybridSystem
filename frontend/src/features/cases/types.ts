/**
 * Case Feature Type Definitions
 * 案件管理模块的类型定义
 */

import { z } from 'zod'

// ============================================================================
// 枚举类型
// ============================================================================

export type SimpleCaseType = 'civil' | 'administrative' | 'criminal' | 'execution' | 'bankruptcy'

export type CaseStatus = 'active' | 'closed'

export type CaseStage =
  | 'first_trial'
  | 'second_trial'
  | 'enforcement'
  | 'labor_arbitration'
  | 'administrative_review'
  | 'private_prosecution'
  | 'investigation'
  | 'prosecution_review'
  | 'retrial_first'
  | 'retrial_second'
  | 'apply_retrial'
  | 'rehearing_first'
  | 'rehearing_second'
  | 'review'
  | 'death_penalty_review'
  | 'petition'
  | 'apply_protest'
  | 'petition_protest'

export type LegalStatus =
  | 'plaintiff'
  | 'defendant'
  | 'third'
  | 'applicant'
  | 'respondent'
  | 'criminal_defendant'
  | 'victim'
  | 'appellant'
  | 'appellee'
  | 'orig_plaintiff'
  | 'orig_defendant'
  | 'orig_third'

export type AuthorityType = 'investigation' | 'prosecution' | 'trial' | 'detention'

export type CaseLogReminderType =
  | 'hearing'
  | 'asset_preservation'
  | 'evidence_deadline'
  | 'statute_limitations'
  | 'appeal_period'
  | 'other'

// ============================================================================
// i18n 标签常量
// ============================================================================

interface I18nLabel {
  zh: string
  en: string
}

export const SIMPLE_CASE_TYPE_LABELS: Record<SimpleCaseType, I18nLabel> = {
  civil: { zh: '民事', en: 'Civil' },
  administrative: { zh: '行政', en: 'Administrative' },
  criminal: { zh: '刑事', en: 'Criminal' },
  execution: { zh: '申请执行', en: 'Execution' },
  bankruptcy: { zh: '破产', en: 'Bankruptcy' },
}

export const CASE_STATUS_LABELS: Record<CaseStatus, I18nLabel> = {
  active: { zh: '在办', en: 'Active' },
  closed: { zh: '已结案', en: 'Closed' },
}

export const CASE_STAGE_LABELS: Record<CaseStage, I18nLabel> = {
  first_trial: { zh: '一审', en: 'First Trial' },
  second_trial: { zh: '二审', en: 'Second Trial' },
  enforcement: { zh: '执行', en: 'Enforcement' },
  labor_arbitration: { zh: '劳动仲裁', en: 'Labor Arbitration' },
  administrative_review: { zh: '行政复议', en: 'Administrative Review' },
  private_prosecution: { zh: '自诉', en: 'Private Prosecution' },
  investigation: { zh: '侦查', en: 'Investigation' },
  prosecution_review: { zh: '审查起诉', en: 'Prosecution Review' },
  retrial_first: { zh: '重审一审', en: 'Retrial First Instance' },
  retrial_second: { zh: '重审二审', en: 'Retrial Second Instance' },
  apply_retrial: { zh: '申请再审', en: 'Apply for Retrial' },
  rehearing_first: { zh: '再审一审', en: 'Rehearing First Instance' },
  rehearing_second: { zh: '再审二审', en: 'Rehearing Second Instance' },
  review: { zh: '提审', en: 'Review' },
  death_penalty_review: { zh: '死刑复核程序', en: 'Death Penalty Review' },
  petition: { zh: '申诉', en: 'Petition' },
  apply_protest: { zh: '申请抗诉', en: 'Apply for Protest' },
  petition_protest: { zh: '申诉抗诉', en: 'Petition Protest' },
}

export const LEGAL_STATUS_LABELS: Record<LegalStatus, I18nLabel> = {
  plaintiff: { zh: '原告', en: 'Plaintiff' },
  defendant: { zh: '被告', en: 'Defendant' },
  third: { zh: '第三人', en: 'Third Party' },
  applicant: { zh: '申请人', en: 'Applicant' },
  respondent: { zh: '被申请人', en: 'Respondent' },
  criminal_defendant: { zh: '被告人', en: 'Criminal Defendant' },
  victim: { zh: '被害人', en: 'Victim' },
  appellant: { zh: '上诉人', en: 'Appellant' },
  appellee: { zh: '被上诉人', en: 'Appellee' },
  orig_plaintiff: { zh: '原审原告', en: 'Original Plaintiff' },
  orig_defendant: { zh: '原审被告', en: 'Original Defendant' },
  orig_third: { zh: '原审第三人', en: 'Original Third Party' },
}

export const AUTHORITY_TYPE_LABELS: Record<AuthorityType, I18nLabel> = {
  investigation: { zh: '侦查机关', en: 'Investigation Authority' },
  prosecution: { zh: '审查起诉机关', en: 'Prosecution Authority' },
  trial: { zh: '审理机构', en: 'Trial Authority' },
  detention: { zh: '当前关押地点', en: 'Detention Facility' },
}

export const CASE_LOG_REMINDER_TYPE_LABELS: Record<CaseLogReminderType, I18nLabel> = {
  hearing: { zh: '开庭', en: 'Hearing' },
  asset_preservation: { zh: '财产保全', en: 'Asset Preservation' },
  evidence_deadline: { zh: '举证期限', en: 'Evidence Deadline' },
  statute_limitations: { zh: '时效', en: 'Statute of Limitations' },
  appeal_period: { zh: '上诉期', en: 'Appeal Period' },
  other: { zh: '其他', en: 'Other' },
}

// ============================================================================
// 关联实体接口
// ============================================================================

export interface LawyerDetail {
  id: number
  username: string
  real_name: string | null
  phone: string | null
}

export interface ClientDetail {
  id: number
  name: string
  client_type: string
  phone: string | null
  id_number: string | null
}

// ============================================================================
// 实体接口
// ============================================================================

export interface Case {
  id: number
  name: string
  status: string | null
  is_filed: boolean
  case_type: SimpleCaseType | null
  start_date: string
  effective_date: string | null
  target_amount: number | null
  preservation_amount: number | null
  cause_of_action: string | null
  current_stage: string | null
  contract_id: number | null
  filing_number?: string | null
  parties: CaseParty[]
  assignments: CaseAssignment[]
  logs: CaseLog[]
  case_numbers: CaseNumber[]
  supervising_authorities: SupervisingAuthority[]
}

export interface CaseInput {
  name: string
  status?: string
  is_filed?: boolean
  case_type?: SimpleCaseType
  target_amount?: number | null
  preservation_amount?: number | null
  cause_of_action?: string | null
  current_stage?: string | null
  effective_date?: string | null
}

export interface CaseUpdate {
  name?: string
  status?: string
  is_filed?: boolean
  case_type?: string
  target_amount?: number | null
  preservation_amount?: number | null
  cause_of_action?: string | null
  current_stage?: string | null
  effective_date?: string | null
}

export interface CaseCreateFull {
  case: CaseInput
  parties?: { client_id: number; legal_status?: string }[]
  assignments?: { lawyer_id: number }[]
  logs?: { content: string; reminder_type?: string; reminder_time?: string }[]
  supervising_authorities?: { name?: string; authority_type?: string }[]
}

export interface CaseParty {
  id: number
  case: number
  client: number
  legal_status: string | null
  client_detail: ClientDetail
}

export interface CaseAssignment {
  id: number
  case: number
  lawyer: number
  lawyer_detail: LawyerDetail
}

export interface CaseLogAttachment {
  id: number
  log: number
  file_path: string | null
  media_url: string | null
  uploaded_at: string
}

export interface CaseLogReminder {
  id: number
  reminder_type: string
  due_at: string
  is_completed: boolean
}

export interface CaseLog {
  id: number
  case: number
  content: string
  actor: number
  actor_detail: LawyerDetail
  attachments: CaseLogAttachment[]
  reminders: CaseLogReminder[]
  created_at: string
  updated_at: string
}

export interface CaseNumber {
  id: number
  number: string
  remarks: string | null
  created_at: string
}

export interface SupervisingAuthority {
  id: number
  name: string | null
  authority_type: string | null
  authority_type_display: string | null
  created_at: string
}

// ============================================================================
// 参考数据接口
// ============================================================================

export interface CauseItem {
  id: string
  name: string
  code?: string
  raw_name?: string
}

export interface CauseTreeNode {
  id: number
  code: string
  name: string
  case_type: string
  level: number
  has_children: boolean
  full_path: string
}

export interface CourtItem {
  id: string
  name: string
}

export interface FeeCalculationRequest {
  target_amount?: number
  preservation_amount?: number
  case_type?: string
  cause_of_action?: string
  cause_of_action_id?: number
}

export interface FeeCalculationResponse {
  acceptance_fee: number | null
  acceptance_fee_half: number | null
  preservation_fee: number | null
  execution_fee: number | null
  payment_order_fee: number | null
  bankruptcy_fee: number | null
  divorce_fee: number | null
  personality_rights_fee: number | null
  ip_fee: number | null
  fixed_fee: number | null
  fee_name: string | null
  special_case_type: string | null
  fee_display_text: string | null
  fee_range_min: number | null
  fee_range_max: number | null
  show_acceptance_fee: boolean
  show_half_fee: boolean
  show_payment_order_fee: boolean
}

// ============================================================================
// Zod 验证 Schema
// ============================================================================

export const caseFormSchema = z.object({
  name: z.string().min(1, { message: '案件名称不能为空' }),
  case_type: z.enum(['civil', 'administrative', 'criminal', 'execution', 'bankruptcy']).optional(),
  status: z.enum(['active', 'closed']).default('active'),
  cause_of_action: z.string().nullable().optional(),
  current_stage: z.string().nullable().optional(),
  target_amount: z.number().nonnegative().nullable().optional(),
  preservation_amount: z.number().nonnegative().nullable().optional(),
  effective_date: z.string().nullable().optional(),
})

export type CaseFormData = z.infer<typeof caseFormSchema>

// ============================================================================
// 筛选参数类型
// ============================================================================

export interface CaseListParams {
  case_type?: SimpleCaseType
  status?: string
  case_number?: string
}
