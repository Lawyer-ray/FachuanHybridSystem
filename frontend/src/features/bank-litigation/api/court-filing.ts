import { createApiClient } from '@/lib/api'
import type { components } from '@/types/api-schema'

// ───────────────────────── 一张网立案 ─────────────────────────

export const courtFilingApi = createApiClient({ prefix: '/api/v1/court-filing' })

/** 立案所需信息（含「我们是不是原告方」「有没有法院凭证」等前置判断） */
export type CaseFilingInfo = components['schemas']['CaseFilingInfoOut']

export async function getCaseFilingInfo(caseId: number): Promise<CaseFilingInfo> {
  return courtFilingApi.get(`case-info/${caseId}`).json<CaseFilingInfo>()
}

export type ExecuteCourtFilingIn = components['schemas']['ExecuteCourtFilingIn']
export type ExecuteCourtFilingOut = components['schemas']['ExecuteCourtFilingOut']

/** 执行一张网在线立案（后台线程） */
export async function executeCourtFiling(
  payload: ExecuteCourtFilingIn,
): Promise<ExecuteCourtFilingOut> {
  return courtFilingApi.post('execute', { json: payload }).json<ExecuteCourtFilingOut>()
}

/** 轮询一张网立案会话 */
export async function getCourtFilingSession(
  sessionId: number,
): Promise<ExecuteCourtFilingOut> {
  return courtFilingApi.get(`session/${sessionId}`).json<ExecuteCourtFilingOut>()
}
