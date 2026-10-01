/**
 * 办案主页的类型：后端投影（消费子集）+ 前端域模型。
 *
 * 后端契约要点（见 backend apps/contracts、apps/cases、apps/organization）：
 * - 三个列表接口都返回**裸数组**，无分页包装；合同量级 ~150，全量拉取做客户端筛选。
 * - display / code 混用陷阱：
 *   · 合同的 fee_mode、representation_stages 返回的是**中文标签**（"固定收费"/"一审"），非代码值；
 *   · /cases/cases 的 status（"在办"）、current_stage、parties[].legal_status 也是**中文标签**。
 * - /organization/lawyers 内部硬分页 page_size=20，律师多于 20 人时拿不全
 *   （本页仅用它补执业证号/律所，缺失时静默降级，不阻塞主列表）。
 */

/* ============ 后端投影：/api/v1/contracts/contracts ============ */

export interface ClientLite {
  id: number
  name: string
  is_our_client: boolean
  phone: string | null
  address: string | null
  client_type_label: string | null
  id_number: string | null
  legal_representative: string | null
}

export interface ContractParty {
  id: number
  /** 中文标签：委托人 / 受益人 / 对方当事人 */
  role_label: string | null
  client_detail: ClientLite | null
}

export interface ContractReminder {
  id: number
  content: string
  due_at: string | null
  reminder_type_label: string | null
}

export interface ContractPayment {
  id: number
  amount: number
  received_at: string | null
  invoice_status_label: string | null
  note: string | null
}

export interface ClientPaymentRecord {
  id: number
  amount: number
  created_at: string
  note: string | null
}

export interface SupplementaryAgreement {
  id: number
  name: string
  created_at: string
  parties: Array<{ id: number; client_name: string | null; is_our_client: boolean }>
}

export interface ContractAssignment {
  id: number
  lawyer_id: number
  lawyer_name: string | null
  is_primary: boolean
}

export interface PrimaryLawyer {
  id: number
  real_name: string | null
  phone: string | null
  law_firm_name: string | null
}

export interface ContractListItem {
  id: number
  /** 合同名 = 委托人主名称（办案主页的主视觉） */
  name: string
  case_type: string
  case_type_label: string | null
  /** unsigned / active / archived */
  status: string
  status_label: string | null
  specified_date: string | null
  start_date: string | null
  end_date: string | null
  is_filed: boolean
  filing_number: string | null
  /** 中文标签（"固定收费"等），非代码值 */
  fee_mode: string | null
  fixed_amount: number | string | null
  risk_rate: number | string | null
  custom_terms: string | null
  /** 中文标签数组（"一审"等） */
  representation_stages: string[]
  law_firm_oa_url: string | null
  law_firm_oa_case_number: string | null
  total_received: number | null
  total_invoiced: number | null
  unpaid_amount: number | null
  contract_parties: ContractParty[]
  assignments: ContractAssignment[]
  primary_lawyer: PrimaryLawyer | null
  reminders: ContractReminder[]
  payments: ContractPayment[]
  client_payment_records: ClientPaymentRecord[]
  supplementary_agreements: SupplementaryAgreement[]
}

/* ============ 后端投影：/api/v1/cases/cases ============ */

export interface CaseNumberOut {
  id: number
  number: string
}

export interface SupervisingAuthorityOut {
  id: number
  name: string
  authority_type_display: string
}

export interface CaseLogActor {
  id: number
  real_name: string | null
  username: string
}

export interface CaseLogOut {
  id: number
  content: string
  created_at: string
  actor_detail: CaseLogActor | null
  attachments: Array<{ id: number }>
  reminder_time: string | null
}

export interface CaseContactOut {
  id: number
  name: string
  role_display: string | null
  phone: string | null
  note: string | null
  stage_display: string | null
}

export interface CasePartyOut {
  id: number
  /** 中文标签（"原告"/"被告"等） */
  legal_status: string | null
  client_detail: ClientLite | null
}

export interface CaseListItem {
  id: number
  /** 关联合同的外键；为空表示未挂到合同（本页不消费） */
  contract_id: number | null
  name: string
  /** 中文标签（"在办"/"已结案"），非代码值 */
  status: string | null
  /** 中文标签（"一审"等），非代码值 */
  current_stage: string | null
  case_numbers: CaseNumberOut[]
  supervising_authorities: SupervisingAuthorityOut[]
  cause_of_action: string | null
  target_amount: number | string | null
  preservation_amount: number | string | null
  start_date: string | null
  effective_date: string | null
  parties: CasePartyOut[]
  logs: CaseLogOut[]
  contacts: CaseContactOut[]
}

/* ============ 后端投影：/api/v1/organization/lawyers ============ */

export interface LawyerListItem {
  id: number
  username: string
  real_name: string | null
  phone: string | null
  license_no: string | null
  law_firm_detail: { id: number; name: string } | null
}

/* ============ 前端域模型（buildDeals 合并产物） ============ */

/** 案件日志（时间倒序、提醒语义已归一） */
export interface DealLog {
  when: string
  who: string
  text: string
  attN: number
  rem: string
  remToday: boolean
}

export interface DealContact {
  name: string
  role: string
  phone: string
  note: string
  stage: string
}

/** 合同名下的个案（程序链节点） */
export interface DealCase {
  id: number
  name: string
  proc: string
  ref: string
  numbers: string[]
  st: string
  done: boolean
  auth: string
  auths: string[]
  cause: string
  target: number | null
  preserv: number | null
  from: string
  partyRows: string[]
  logs: DealLog[]
  contacts: DealContact[]
}

/** 抽屉里的当事人行（含复制用全字段） */
export interface DealParty {
  name: string
  role: string
  type: string
  idno: string
  legalRep: string
  phone: string
  address: string
  ours: boolean
}

/** 抽屉里的承办律师行 */
export interface DealTeamMember {
  name: string
  primary: boolean
  phone: string
  license: string
  firm: string
}

export interface DealReminder {
  t: string
  dueFull: string
  type: string
}

/** 办案主页一行 = 一份委托合同（含关联案件/当事人/团队/款项聚合） */
export interface WorkbenchDeal {
  id: number
  /** 是否诉讼类（civil/criminal/administrative/labor/intl） */
  lit: boolean
  client: string
  ctype: string
  no: string
  amount: string | null
  amountNum: number | null
  fee: string
  from: string
  to: string
  daysLeft: number | null
  status: string
  statusLabel: string
  specified: string
  isFiled: boolean
  filingNo: string
  oaUrl: string
  customTerms: string
  /** 列表副行：我方 / 对方 各取第一位 */
  parties: { client: string; other: string }
  /** 抽屉全量当事人（我方在前） */
  partiesAll: DealParty[]
  team: DealTeamMember[]
  primaryPhone: string
  cases: DealCase[]
  work: DealReminder[]
  riskRate: number | string | null
  stages: string[]
  primary: string
  lawFirm: string
  totalReceived: string | null
  totalInvoiced: string | null
  unpaid: string | null
  payments: ContractPayment[]
  payRecords: ClientPaymentRecord[]
  supps: SupplementaryAgreement[]
}

/** 列表筛选状态（默认：在办 + 全部类目 + 全部收费） */
export interface WorkbenchFilter {
  status: '' | 'active' | 'archived' | 'unsigned'
  cat: string
  fee: string
  q: string
}
