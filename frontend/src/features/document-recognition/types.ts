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

/** 日期候选（生成物 DateCandidateOutSchema；status 收窄为后端三态枚举，供 CandidateRow 直接消费） */
export type DateCandidate = Omit<components['schemas']['DateCandidateOutSchema'], 'status'> & {
  status: 'pending' | 'confirmed' | 'skipped'
}

/** 案件绑定推荐（生成物 CaseRecommendationOutSchema） */
export type CaseRecommendation = components['schemas']['CaseRecommendationOutSchema']

/** 文书联系人（后端读时从原文提取；生成物 ContactOutSchema） */
export type ContactInfo = components['schemas']['ContactOutSchema']

/** GET court-document/task/{task_id} 的响应（生成物 TaskStatusResponseSchema；
 *  仅 date_candidates 覆写为收窄版 DateCandidate[]，其余字段原样） */
export type TaskOut = Omit<components['schemas']['TaskStatusResponseSchema'], 'date_candidates'> & {
  date_candidates: DateCandidate[]
}

/** GET court-document/search-cases 的响应行（生成物 CaseSearchResultSchema） */
export type CaseSearchItem = components['schemas']['CaseSearchResultSchema']

/** POST task/{id}/dates/confirm 的单条请求项（生成物 DateConfirmItemInSchema） */
export type ConfirmItemIn = components['schemas']['DateConfirmItemInSchema']

/** POST task/{id}/dates/confirm 的单条结果（生成物 DateConfirmItemOutSchema） */
export type ConfirmItemOut = components['schemas']['DateConfirmItemOutSchema']
