/**
 * 到账待认领（Payment Intake）数据模型。
 *
 * 字段与后端 openapi 生成物一一对应，不手抄字段名——接口前缀已实测为
 * `/api/v1/contracts/finance/intake`（含 `/contracts` 挂载前缀，见 api.ts）。
 */

/** 候选判定类别（后端 contract_match_v2 的 kind） */
export type CandidateKind = 'exact' | 'partial' | 'amount_only'

/** 待认领状态 */
export type IntakeStatus = 'pending' | 'confirmed' | 'rejected' | 'ignored'

/** 系统给出的候选项目 */
export interface IntakeCandidate {
  contract_id: number
  contract_name: string
  kind: CandidateKind
  score: number
  reasons: string[]
  outstanding_amount: string | null
  fee_mode: string
  caveat: string
}

/**
 * 被资格规则排除、但有关联线索的项目。
 *
 * 这是本功能的关键设计：已收满/已归档的项目**不参与匹配**，但系统仍会把
 * 「想到过它、为什么排除」告诉人，避免线索丢失。
 */
export interface ExcludedHint {
  contract_id: number
  contract_name: string
  excluded_by: 'fully_paid' | 'archived' | 'unsigned' | 'case_closed'
  note: string
}

/** 一条待认领款项 */
export interface Intake {
  id: number
  amount: string
  received_at: string
  payer_name: string
  on_behalf_of: string
  display_payer: string
  status: IntakeStatus
  status_label: string
  bank_remark: string
  suggested_contract_id: number | null
  suggested_contract_name: string | null
  confirmed_contract_id: number | null
  confirmed_contract_name: string | null
  payment_id: number | null
  decision_note: string
  candidates: IntakeCandidate[]
  excluded_hints: ExcludedHint[]
  inbox_message_id: number
  subject: string
  sender: string
}

/** 「换个项目」下拉项 */
export interface SelectableContract {
  id: number
  name: string
  fee_mode: string
  fixed_amount: string | null
  paid_total: string | null
  outstanding_amount: string | null
  expires_note: string
}

/** 操作（确认/驳回/忽略/撤销）的返回 */
export interface IntakeActionResult {
  success: boolean
  message: string
  intake_id: number
  status: IntakeStatus
  payment_id: number | null
}
