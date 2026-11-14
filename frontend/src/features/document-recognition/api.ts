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

/** 上传文书并提交异步识别，立即返回 task_id。
 *
 * `sourceCourtSmsId` 走**管线模式**（后端 `source_court_sms_id` 表单字段）：案件与
 * 案件日志由法院短信侧预绑定，识别只做提取 + 日期候选，不重复建日志/重命名/通知。
 * 记一笔的独立上传不传，行为不变。 */
export async function recognizeFile(
  file: File,
  opts?: { sourceCourtSmsId?: number },
): Promise<TaskSubmitId> {
  const body = new FormData()
  body.append('file', file)
  if (opts?.sourceCourtSmsId != null) body.append('source_court_sms_id', String(opts.sourceCourtSmsId))
  return documentRecognitionApi
    .post('court-document/recognize', { body, timeout: UPLOAD_TIMEOUT_MS })
    .json<components['schemas']['TaskSubmitResponseSchema']>()
}

/** POST court-document/sms/{id}/capture-dates 的响应（生成物 DateCaptureOutSchema） */
export type DateCaptureOut = components['schemas']['DateCaptureOutSchema']

/** GET court-document/sms/{id}/capture-status 的响应（生成物 SourceTasksOutSchema） */
export type SourceTasksOut = components['schemas']['SourceTasksOutSchema']

/**
 * 把某条法院短信的文书送去「记一笔」识别关键日期（**幂等**）。
 *
 * 短信弹窗一打开就自动调一次：已有任务直接复用（不重复烧 LLM），失败的任务
 * 原地重跑。`force` 只给「重新识别」按钮用（无条件新建任务）。
 *
 * 旁线纪律：该接口不改变法院短信（CourtSMS）任何状态，识别失败不影响短信主线。
 */
export async function captureCourtSmsDates(smsId: number, opts?: { force?: boolean }): Promise<DateCaptureOut> {
  return documentRecognitionApi
    .post(`court-document/sms/${smsId}/capture-dates`, {
      searchParams: opts?.force ? { force: 'true' } : {},
      // 建任务要查文件/落库 + 投递队列，给比普通请求宽的窗口（仍远快于识别本身）
      timeout: 30_000,
    })
    .json<DateCaptureOut>()
}

/** 某条法院短信派生出的识别任务（轮询到识别完成 + 「继续确认」入口） */
export async function getCourtSmsCaptureStatus(smsId: number): Promise<SourceTasksOut> {
  return documentRecognitionApi.get(`court-document/sms/${smsId}/capture-status`).json<SourceTasksOut>()
}

/** 查询任务状态与结果（含日期候选、绑定推荐） */
export async function getTask(taskId: number): Promise<TaskOut> {
  return documentRecognitionApi.get(`court-document/task/${taskId}`).json<TaskOut>()
}

/**
 * 重跑识别（复用同一个已存文件，不重新上传）。
 *
 * 后端只允许 failed / 疑似僵死的 processing 重跑；已成功或仍在正常跑的任务
 * 会返回业务错误（TASK_ALREADY_SUCCESS / TASK_STILL_RUNNING）。
 */
export async function retryTask(taskId: number): Promise<TaskOut> {
  return documentRecognitionApi.post(`court-document/task/${taskId}/retry`).json<TaskOut>()
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
