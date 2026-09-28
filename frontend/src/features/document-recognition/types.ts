/** 文书识别域类型（/api/v1/document-recognition）。 */

/** 提醒类型（与后端 ReminderType 对齐的白名单子集） */
export type ReminderTypeCode =
  | 'hearing'
  | 'asset_preservation_expires'
  | 'evidence_deadline'
  | 'appeal_deadline'
  | 'payment_deadline'
  | 'submission_deadline'
  | 'other'

export interface RecognitionInfo {
  document_type: string | null
  case_number: string | null
  key_time: string | null
  confidence: number | null
  extraction_method: string | null
  llm_model: string | null
  llm_backend: string | null
  llm_latency_ms: number | null
  degraded: boolean | null
}

export interface BindingInfo {
  success: boolean | null
  case_id: number | null
  case_name: string | null
  case_log_id: number | null
  message: string | null
  error_code: string | null
}

export interface DateCandidate {
  id: number
  due_at: string
  reminder_type: string
  reminder_type_label: string
  context_text: string
  source: string
  confidence: number | null
  status: 'pending' | 'confirmed' | 'skipped'
  reminder_id: number | null
  confirmed_at: string | null
}

export interface CaseRecommendation {
  case_id: number
  case_name: string
  score: number
  reasons: string[]
  case_numbers: string[]
  parties: string[]
  status: string
}

export interface TaskOut {
  task_id: number
  status: 'pending' | 'processing' | 'success' | 'failed'
  file_path: string | null
  recognition: RecognitionInfo | null
  binding: BindingInfo | null
  date_candidates: DateCandidate[]
  recommendations: CaseRecommendation[]
  binding_mode: 'standalone' | 'pipeline'
  date_confirmation_status: string | null
  error_message: string | null
  created_at: string
  finished_at: string | null
}

export interface CaseSearchItem {
  id: number
  name: string
  case_numbers: string[]
  parties: string[]
}

export interface ConfirmItemIn {
  candidate_id: number
  action: 'confirm' | 'skip'
  /** naive 本地 ISO（datetime-local 原文），服务端 make_aware */
  due_at?: string
  reminder_type?: string
}

export interface ConfirmItemOut {
  candidate_id: number
  status: string
  reminder_id: number | null
  message: string
  error_code: string | null
}
