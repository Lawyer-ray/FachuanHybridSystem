import { createFeatureApiClient } from '@/lib/api'
import type { MessageSource } from './types'

const api = createFeatureApiClient('inbox')

export const messageSourceApi = {
  list: (): Promise<MessageSource[]> => api.get('sources').json(),
  get: (id: number): Promise<MessageSource> => api.get(`sources/${id}`).json(),
  create: (data: { display_name: string; source_type: string; credential_id: number; is_enabled?: boolean; poll_interval_minutes?: number }): Promise<MessageSource> =>
    api.post('sources', { json: data }).json(),
  update: (id: number, data: Partial<{ display_name: string; is_enabled: boolean; poll_interval_minutes: number; sender_whitelist: string; sender_blacklist: string }>): Promise<MessageSource> =>
    api.put(`sources/${id}`, { json: data }).json(),
  delete: (id: number) => api.delete(`sources/${id}`),
  sync: (id: number): Promise<{ success: boolean; message: string }> =>
    api.post(`sources/${id}/sync`).json(),
  syncAll: (): Promise<{ success: boolean; message: string }> =>
    api.post('sources/sync-all').json(),
}
