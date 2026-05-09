import { api } from '@/lib/api'
import type { OAConfig, FilingSession } from '../types'

export const oaApi = {
  fetchConfigs: async (): Promise<OAConfig[]> =>
    api.get('oa-filing/configs').json<OAConfig[]>(),

  execute: async (siteName: string, contractId: number, caseId?: number): Promise<FilingSession> =>
    api.post('oa-filing/execute', { json: { site_name: siteName, contract_id: contractId, case_id: caseId ?? null } }).json<FilingSession>(),

  getSession: async (sessionId: number): Promise<FilingSession> =>
    api.get(`oa-filing/session/${sessionId}`).json<FilingSession>(),
}
