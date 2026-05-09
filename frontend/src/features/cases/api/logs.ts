import { createFeatureApiClient } from '@/lib/api'
import type { CaseLog, CaseLogAttachment, CaseNumber } from '../types'

type CreateCaseNumberInput = Pick<CaseNumber, 'number'> & Partial<Omit<CaseNumber, 'id' | 'created_at'>>
type UpdateCaseNumberInput = Partial<Omit<CaseNumber, 'id' | 'created_at'>>

const client = createFeatureApiClient('cases')

export const logsApi = {
  list: async (caseId: number | string): Promise<CaseLog[]> =>
    client.get('logs', { searchParams: { case_id: String(caseId) } }).json<CaseLog[]>(),

  listAll: async (): Promise<CaseLog[]> =>
    client.get('logs').json<CaseLog[]>(),

  create: async (data: { case_id: number; content: string; reminder_type?: string; reminder_time?: string }): Promise<CaseLog> =>
    client.post('logs', { json: data }).json<CaseLog>(),

  update: async (id: number | string, data: { case_id?: number; content?: string }): Promise<CaseLog> =>
    client.put(`logs/${id}`, { json: data }).json<CaseLog>(),

  delete: async (id: number | string): Promise<void> => {
    await client.delete(`logs/${id}`)
  },

  uploadAttachments: async (logId: number | string, files: File[]): Promise<CaseLogAttachment[]> => {
    const formData = new FormData()
    files.forEach((file) => formData.append('files', file))
    return client.post(`logs/${logId}/attachments`, { body: formData }).json<CaseLogAttachment[]>()
  },

  listCaseNumbers: async (caseId: number | string): Promise<CaseNumber[]> =>
    client.get('case-numbers', { searchParams: { case_id: String(caseId) } }).json<CaseNumber[]>(),

  createCaseNumber: async (data: CreateCaseNumberInput): Promise<CaseNumber> =>
    client.post('case-numbers', { json: data }).json<CaseNumber>(),

  updateCaseNumber: async (id: number | string, data: UpdateCaseNumberInput): Promise<CaseNumber> =>
    client.put(`case-numbers/${id}`, { json: data }).json<CaseNumber>(),

  deleteCaseNumber: async (id: number | string): Promise<void> => {
    await client.delete(`case-numbers/${id}`)
  },
}
