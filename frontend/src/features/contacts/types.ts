/**
 * Contacts Feature Type Definitions
 * 工作人员联系方式模块的类型定义
 */

export type ContactRole =
  | 'presiding_judge'
  | 'judge'
  | 'clerk'
  | 'judge_assistant'
  | 'prosecutor'
  | 'police'
  | 'arbitrator'
  | 'mediator'
  | 'other'

interface I18nLabel {
  zh: string
  en: string
}

export const CONTACT_ROLE_LABELS: Record<ContactRole, I18nLabel> = {
  presiding_judge: { zh: '审判长', en: 'Presiding Judge' },
  judge: { zh: '审判员/法官', en: 'Judge' },
  clerk: { zh: '书记员', en: 'Clerk' },
  judge_assistant: { zh: '法官助理', en: 'Judge Assistant' },
  prosecutor: { zh: '检察官', en: 'Prosecutor' },
  police: { zh: '警官', en: 'Police Officer' },
  arbitrator: { zh: '仲裁员', en: 'Arbitrator' },
  mediator: { zh: '调解员', en: 'Mediator' },
  other: { zh: '其他', en: 'Other' },
}

export interface CaseContact {
  id: number
  case_id: number
  authority_id: number | null
  authority_name: string | null
  name: string
  role: ContactRole
  role_display: string | null
  phone: string | null
  address: string | null
  stage: string | null
  stage_display: string | null
  note: string | null
  created_at: string
  updated_at: string
}

export interface CaseContactInput {
  case_id: number
  authority_id?: number | null
  name: string
  role: ContactRole
  phone?: string | null
  address?: string | null
  stage?: string | null
  note?: string | null
}

export interface CaseContactSearchResult {
  authority_name: string | null
  name: string
  role: string
  role_display: string | null
  phone: string | null
  address: string | null
  occurrence_count: number
  case_ids: number[]
}
