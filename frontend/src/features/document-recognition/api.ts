/** 文书识别 API 客户端（/api/v1/document-recognition，JWT 自动携带）。 */

import { createApiClient, UPLOAD_TIMEOUT_MS } from '@/lib/api'
import type { components } from '@/types/api-schema'

import type { CaseSearchItem, ConfirmItemIn, TaskOut } from './types'

export const documentRecognitionApi = createApiClient({ prefix: '/api/v1/document-recognition' })

/** POST court-document/recognize 的响应（生成物 TaskSubmitResponseSchema；
 *  对外只暴露消费的 task_id 投影） */
type TaskSubmitId = Pick<components['schemas']['TaskSubmitResponseSchema'], 'task_id'>

/** POST court-document/task/{id}/dates/confirm 的响应（生成物 DateConfirmResponseSchema） */
type DateConfirmResponse = components['schemas']['DateConfirmResponseSchema']

/** 上传文书并提交异步识别，立即返回 task_id */
export async function recognizeFile(file: File): Promise<TaskSubmitId> {
  const body = new FormData()
  body.append('file', file)
  return documentRecognitionApi
    .post('court-document/recognize', { body, timeout: UPLOAD_TIMEOUT_MS })
    .json<components['schemas']['TaskSubmitResponseSchema']>()
}

/** 查询任务状态与结果（含日期候选、绑定推荐） */
export async function getTask(taskId: number): Promise<TaskOut> {
  return documentRecognitionApi.get(`court-document/task/${taskId}`).json<TaskOut>()
}

/** 手动绑定案件 */
export async function bindTask(taskId: number, caseId: number): Promise<void> {
  await documentRecognitionApi.post(`court-document/task/${taskId}/bind`, { json: { case_id: caseId } })
}

/** 批量确认/忽略日期候选（确认后才写入重要日期提醒） */
export async function confirmDates(taskId: number, items: ConfirmItemIn[]): Promise<DateConfirmResponse> {
  return documentRecognitionApi
    .post(`court-document/task/${taskId}/dates/confirm`, { json: { items } })
    .json<DateConfirmResponse>()
}

/** 撤销确认：删除本功能创建的提醒，候选回到待确认 */
export async function revokeDate(taskId: number, candidateId: number): Promise<void> {
  await documentRecognitionApi.post(`court-document/task/${taskId}/dates/${candidateId}/revoke`)
}

/** 搜索可绑定案件（本域自有的 search-cases 端点；空词返回全部在办）。
 *  跨域消费方（如 home 的法院短信人工分配）经 index.ts 出口复用。 */
export async function searchCasesForBinding(
  q: string,
  opts?: { limit?: number; signal?: AbortSignal },
): Promise<CaseSearchItem[]> {
  return documentRecognitionApi
    .get('court-document/search-cases', {
      searchParams: { q, limit: String(opts?.limit ?? 10) },
      signal: opts?.signal,
    })
    .json<CaseSearchItem[]>()
}
