/**
 * Settings API — Task Queue + System Config
 */

import { createApiClient } from '@/lib/api'

export interface QueuedTask {
  id: string
  name: string
  func: string
  group: string | null
  created_at: string | null
}

export interface CompletedTask {
  id: string
  name: string
  func: string
  group: string | null
  started_at: string | null
  finished_at: string | null
  duration: number | null
  success: boolean
  result: string | null
}

export interface ScheduledTask {
  id: number
  name: string
  func: string
  schedule_type: string
  repeats: number
  next_run: string | null
  last_run: string | null
}

const api = createApiClient({
  prefixUrl: `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002/api/v1'}/task-queue`,
})

export const taskQueueApi = {
  listQueued: (): Promise<QueuedTask[]> =>
    api.get('queued').json<QueuedTask[]>(),

  listCompleted: (): Promise<CompletedTask[]> =>
    api.get('completed').json<CompletedTask[]>(),

  listFailed: (): Promise<CompletedTask[]> =>
    api.get('failed').json<CompletedTask[]>(),

  listScheduled: (): Promise<ScheduledTask[]> =>
    api.get('scheduled').json<ScheduledTask[]>(),

  deleteTask: (taskId: string): Promise<{ deleted: number }> =>
    api.delete(`tasks/${taskId}`).json(),

  deleteSchedule: (scheduleId: number): Promise<{ deleted: number }> =>
    api.delete(`schedules/${scheduleId}`).json(),

  resubmitTask: (taskId: string): Promise<{ new_task_id?: string; error?: string }> =>
    api.post(`tasks/${taskId}/resubmit`).json(),
}

// ─── System Config API ─────────────────────────────────────────────────────────

export interface SystemConfigItem {
  key: string
  value: string
  category: string
  description: string
  is_secret: boolean
  is_active: boolean
}

export interface SystemConfigGroup {
  category: string
  items: SystemConfigItem[]
}

const configApi = createApiClient({
  prefixUrl: `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002/api/v1'}/config`,
})

export const systemConfigApi = {
  listConfigs: (): Promise<{ groups: SystemConfigGroup[] }> =>
    configApi.get('system-configs').json(),

  updateConfigs: (category: string, updates: Record<string, string>): Promise<{ success: boolean; updated_count: number }> =>
    configApi.put('system-configs', { json: { category, updates } }).json(),

  createConfig: (data: { key: string; value?: string; category: string; description?: string; is_secret?: boolean }): Promise<SystemConfigItem> =>
    configApi.post('system-configs', { json: data }).json(),

  patchConfig: (key: string, data: { value?: string; category?: string; description?: string; is_secret?: boolean; is_active?: boolean }): Promise<SystemConfigItem> =>
    configApi.patch(`system-configs/${key}`, { json: data }).json(),

  deleteConfig: (key: string): Promise<{ success: boolean }> =>
    configApi.delete(`system-configs/${key}`).json(),
}

export default taskQueueApi
