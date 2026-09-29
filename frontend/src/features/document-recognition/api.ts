/** 文书识别 API 客户端（/api/v1/document-recognition，JWT 自动携带）。 */

import { createApiClient } from '@/lib/api'

import type { CaseSearchItem, ConfirmItemIn, ConfirmItemOut, TaskOut } from './types'

export const documentRecognitionApi = createApiClient({ prefix: '/api/v1/document-recognition' })

/** 上传文书并提交异步识别，立即返回 task_id */
export async function recognizeFile(file: File): Promise<{ task_id: number }> {
  const body = new FormData()
  body.append('file', file)
  return documentRecognitionApi.post('court-document/recognize', { body }).json<{ task_id: number }>()
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
export async function confirmDates(
  taskId: number,
  items: ConfirmItemIn[],
): Promise<{ success: boolean; results: ConfirmItemOut[] }> {
  return documentRecognitionApi
    .post(`court-document/task/${taskId}/dates/confirm`, { json: { items } })
    .json<{ success: boolean; results: ConfirmItemOut[] }>()
}

/** 撤销确认：删除本功能创建的提醒，候选回到待确认 */
export async function revokeDate(taskId: number, candidateId: number): Promise<void> {
  await documentRecognitionApi.post(`court-document/task/${taskId}/dates/${candidateId}/revoke`)
}

/** 搜索可绑定案件（本域自有的 search-cases 端点） */
export async function searchCasesForBinding(q: string): Promise<CaseSearchItem[]> {
  return documentRecognitionApi
    .get('court-document/search-cases', { searchParams: { q, limit: 10 } })
    .json<CaseSearchItem[]>()
}
