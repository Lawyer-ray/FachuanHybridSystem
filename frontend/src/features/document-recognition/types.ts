/** 文书识别域类型（/api/v1/document-recognition）。
 *
 * 端点形状直接取自 openapi-typescript 生成物（src/types/api-schema.d.ts）；
 * 仅在生成物把字段声明为裸 string、而业务需要枚举收窄处做 Omit + 覆写。 */

import type { components } from '@/types/api-schema'

/** 提醒类型（与后端 ReminderType 对齐的白名单子集） */
export type ReminderTypeCode =
  | 'hearing'
  | 'asset_preservation_expires'
  | 'evidence_deadline'
  | 'appeal_deadline'
  | 'payment_deadline'
  | 'submission_deadline'
  | 'other'

/** 识别结果（GET task/{id}.recognition，生成物 RecognitionResultSchema） */
export type RecognitionInfo = components['schemas']['RecognitionResultSchema']

/** 绑定结果（GET task/{id}.binding，生成物 BindingResultSchema） */
export type BindingInfo = components['schemas']['BindingResultSchema']

/** 日期候选（生成物 DateCandidateOutSchema；status 收窄为后端三态枚举，供 CandidateRow 直接消费）。
 *  可解释性字段由后端新增、生成物尚未收录，全部可选（前端一律按缺省值兜底）。 */
export type DateCandidate = Omit<
  components['schemas']['DateCandidateOutSchema'],
  // 生成物把后端带默认值的字段渲染成必填，但历史响应/测试 fixture 可能没有它们：
  // 这几个一律从生成物里摘掉再以可选形式重声明，前端永远按缺省值兜底。
  | 'status'
  | 'anchor_kind'
  | 'anchor_at'
  | 'anchor_document'
  | 'derivation'
  | 'derivation_label'
  | 'review_flags'
  | 'default_checked'
  | 'anchor_note'
  | 'duplicate_of_id'
> & {
  status: 'pending' | 'confirmed' | 'skipped'
  /** 起算点类型 service_of_self / issue_date_of_self / effective_date / foreign_document / unknown */
  anchor_kind?: string
  /** 起算点日期（YYYY-MM-DD） */
  anchor_at?: string | null
  /** 起算点所在文书 self / other_in_batch / future_document / other_case */
  anchor_document?: string
  /** 推导方式 llm_absolute / rule_absolute / rule_period / rule_relative */
  derivation?: string
  /** 后端给的推导中文标签 */
  derivation_label?: string
  /** 复核标记 anchor_effective / generic_boilerplate / low_confidence / far_future / duplicate / discarded_by_gate */
  review_flags?: string[]
  /** 后端算好的默认勾选 */
  default_checked?: boolean
  /** 起算点说明，如「起算点：本份文书送达日 2026-11-24 + 7 天」 */
  anchor_note?: string
  /** 重复项指向的候选 ID */
  duplicate_of_id?: number | null
}

/** 被过滤掉的候选（TaskOut.suppressed_items；字段均可能缺省） */
export interface SuppressedCandidate {
  due_at?: string
  reminder_type?: string
  reminder_type_label?: string
  anchor_document?: string
  reason?: string
  context_text?: string
}

/** 案件绑定推荐（生成物 CaseRecommendationOutSchema） */
export type CaseRecommendation = components['schemas']['CaseRecommendationOutSchema']

/** 文书联系人（后端读时从原文提取；生成物 ContactOutSchema） */
export type ContactInfo = components['schemas']['ContactOutSchema']

/** GET court-document/task/{task_id} 的响应（生成物 TaskStatusResponseSchema；
 *  date_candidates 覆写为收窄版，并补上生成物尚未收录的 suppressed 字段） */
export type TaskOut = Omit<
  components['schemas']['TaskStatusResponseSchema'],
  'date_candidates' | 'suppressed_count' | 'suppressed_items'
> & {
  date_candidates: DateCandidate[]
  /** 被过滤掉的候选条数与明细（后端新增，可能缺省） */
  suppressed_count?: number
  suppressed_items?: SuppressedCandidate[]
}

/** GET court-document/search-cases 的响应行（生成物 CaseSearchResultSchema） */
export type CaseSearchItem = components['schemas']['CaseSearchResultSchema']

/** POST task/{id}/dates/confirm 的单条请求项（生成物 DateConfirmItemInSchema） */
export type ConfirmItemIn = components['schemas']['DateConfirmItemInSchema']

/** POST task/{id}/dates/confirm 的单条结果（生成物 DateConfirmItemOutSchema） */
export type ConfirmItemOut = components['schemas']['DateConfirmItemOutSchema']
