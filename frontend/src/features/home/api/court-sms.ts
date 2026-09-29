import { createApiClient } from '@/lib/api'
import { automationApi } from './tools'
import { API_BASE_URL, withAuthToken } from './download'

/**
 * 法院短信处理链路 API（对接后端 apps/automation，路径已按 OpenAPI 核对）：
 *   - 提交     = POST /automation/court-sms                    （返回 { data: { id, status } }）
 *   - 详情     = GET  /automation/court-sms/{id}               （CourtSMSDetailOut，含案件/文书引用）
 *   - 人工分配 = POST /automation/court-sms/{id}/assign-case   （匹配不到案件时手动指定，随后继续处理）
 *   - 重新处理 = POST /automation/court-sms/{id}/retry         （保留手动绑定案件，仅重跑后续流程）
 *   - 单件下载 = GET  /automation/court-sms/{id}/documents/{ref_index}/download
 *   - 打包下载 = GET  /automation/court-sms/{id}/documents/download-all
 */

/** 后端 CourtSMSDetailOut 的前端投影——只声明弹窗用到的字段 */
export interface CourtSmsDetail {
  id: number
  content: string
  sms_type: string | null
  download_links: string[]
  case_numbers: string[]
  party_names: string[]
  status: string
  error_message: string | null
  retry_count: number
  case: { id: number; name: string } | null
  documents: { id: number | null; name: string; source: string; download_url: string | null }[]
  notification_results: Record<string, unknown> | null
}

/** 单件文书下载地址（带 token，供 <a download> 直链使用；文件名后端已重命名） */
export function courtSmsDocDownloadUrl(smsId: number, refIndex: number): string {
  return withAuthToken(`${API_BASE_URL}/automation/court-sms/${smsId}/documents/${refIndex}/download`)
}

/** 全部文书打包 ZIP 下载地址 */
export function courtSmsDownloadAllUrl(smsId: number): string {
  return withAuthToken(`${API_BASE_URL}/automation/court-sms/${smsId}/documents/download-all`)
}

/** 查询处理详情（轮询用；404 等由调用方 catch） */
export async function getCourtSmsDetail(smsId: number): Promise<CourtSmsDetail> {
  return automationApi.get(`court-sms/${smsId}`).json<CourtSmsDetail>()
}

/** 人工指定案件：成功后状态进入 renaming/notifying，需要继续轮询到终态 */
export async function assignCourtSmsCase(smsId: number, caseId: number): Promise<void> {
  const res = await automationApi
    .post(`court-sms/${smsId}/assign-case`, { json: { case_id: caseId } })
    .json<{ success?: boolean; message?: string }>()
  if (res.success === false) throw new Error(res.message || '指定案件失败')
}

/** 重新处理（匹配失败/下载失败后重跑；已手动绑定的案件会被保留） */
export async function retryCourtSms(smsId: number): Promise<void> {
  await automationApi.post(`court-sms/${smsId}/retry`)
}

/** 删除短信记录（自测造的数据用它清理） */
export async function deleteCourtSms(smsId: number): Promise<void> {
  await automationApi.delete(`court-sms/${smsId}`)
}

/** 案件搜索：复用文书识别域的 search-cases 端点（按名/案号/当事人模糊搜，空词返回全部在办） */
const caseSearchApi = createApiClient({ prefix: '/api/v1/document-recognition' })

export interface CaseSearchItem {
  id: number
  name: string
  case_numbers: string[]
  parties: string[]
}

export async function searchCasesForAssign(q: string, limit = 10): Promise<CaseSearchItem[]> {
  return caseSearchApi
    .get('court-document/search-cases', { searchParams: { q, limit: String(limit) } })
    .json<CaseSearchItem[]>()
}
