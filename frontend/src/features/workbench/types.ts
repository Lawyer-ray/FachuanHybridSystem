/**
 * 办案主页的类型：后端投影（openapi 生成物）+ 前端域模型。
 *
 * 后端契约要点（见 backend apps/contracts、apps/cases、apps/organization）：
 * - 合同走分页接口（GET /contracts/contracts?slim=true，生成物 ContractListPageOut），
 *   案件列表按合同 ID 按需拉取（GET /cases/cases?contract_id=，生成物 CaseOut）；
 *   两端点均已声明 response=，投影直接取生成物，仅覆写个别运行时差异字段。
 * - display / code 混用陷阱：
 *   · 合同的 fee_mode、representation_stages 返回的是**中文标签**（"固定收费"/"一审"），非代码值；
 *   · /cases/cases 的 status（"在办"）、current_stage、parties[].legal_status 也是**中文标签**。
 * - /organization/lawyers 内部硬分页 page_size=20，律师多于 20 人时拿不全
 *   （本页仅用它补执业证号/律所，缺失时静默降级，不阻塞主列表）。
 *   生成物 LawyerOut（organization 全量形状）已含 license_no / law_firm_detail，
 *   LawyerListItem 取其消费投影。
 */

import type { components } from '@/types/api-schema'

type Schemas = components['schemas']

/* ============ 后端投影：/api/v1/contracts/contracts ============ */

export type ClientLite = Schemas['ClientLiteOut']
export type ContractParty = Schemas['ContractPartyOut']
export type ContractReminder = Schemas['ReminderLiteOut']
export type ContractPayment = Schemas['ContractPaymentOut']
export type ClientPaymentRecord = Schemas['ClientPaymentRecordOut']
export type SupplementaryAgreement = Schemas['SupplementaryAgreementOut']
export type ContractAssignment = Schemas['ContractAssignmentOut']
export type PrimaryLawyer = Schemas['ContractLawyerOut']

/**
 * 合同行（slim 投影）。生成物 ContractOut 的三处运行时差异在此覆写：
 * - finalized_materials：slim=true 时后端剔除该键（Omit 掉）；
 * - representation_stages：模型 JSONField 使生成物标成 Record，运行时实为中文标签数组；
 * - id：生成物按 ModelSchema 默认口径可选可空，列表行运行时必有。
 */
export type ContractListItem = Omit<
  Schemas['ContractOut'],
  'finalized_materials' | 'representation_stages' | 'id'
> & {
  representation_stages: string[]
  id: number
}

/* ============ 后端投影：/api/v1/cases/cases ============ */

export type CaseNumberOut = Schemas['CaseNumberOut']
export type SupervisingAuthorityOut = Schemas['SupervisingAuthorityOut']
export type CaseLogActor = Schemas['CaseLogOut']['actor_detail']
export type CaseLogOut = Schemas['CaseLogOut']
export type CaseContactOut = Schemas['CaseContactOut']
export type CasePartyOut = Schemas['CasePartyOut']

/** 案件行：生成物 CaseOut（id 覆写为必有，生成物可选可空） */
export type CaseListItem = Omit<Schemas['CaseOut'], 'id'> & { id: number }

/* ============ 后端投影：/api/v1/organization/lawyers ============ */

/** 律师行（生成物 LawyerOut 的消费投影）。后端已修复 OpenAPI 组件名冲突
 *  （此前 contracts.LawyerOut 与 organization.LawyerOut 同名互踩，生成物缺
 *  license_no / law_firm_detail）；仅取本页消费字段，id 按 ModelSchema
 *  口径覆写为必有（列表行运行时必有）。 */
export type LawyerListItem = Omit<
  Pick<
    Schemas['LawyerOut'],
    'id' | 'username' | 'real_name' | 'phone' | 'license_no' | 'law_firm_detail'
  >,
  'id'
> & { id: number }

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
  /** 案件计数（明细按需加载，见 use-contract-cases） */
  caseCount: number
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

/** 列表筛选状态（默认：在办 + 全部类目 + 全部收费）。cat/fee 存后端代码值，展示用 facets 的 label */
export interface WorkbenchFilter {
  status: '' | 'active' | 'archived' | 'unsigned'
  /** case_type 代码（civil/advisor/…），'' = 全部 */
  cat: string
  /** fee_mode 代码（FIXED/SEMI_RISK/…），'' = 全部 */
  fee: string
  q: string
}

/** facets 单项（生成物 ContractFacetCountOut）：value 供过滤参数、label 供展示 */
export type ContractFacetItem = Schemas['ContractFacetCountOut']

/** 分页列表响应（GET /contracts/contracts?page=N）：一页合同 + 总数 + 全库筛选计数。
 *  本页恒走 slim=true，items 用剔除归档材料的 slim 投影 ContractListItem */
export type ContractPageResponse = Omit<Schemas['ContractListPageOut'], 'items'> & {
  items: ContractListItem[]
}
