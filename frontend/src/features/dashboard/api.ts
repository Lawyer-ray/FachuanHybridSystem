import { createApiClient } from '@/lib/api'
import type { DashboardStats } from './types'

const api = createApiClient({
  prefixUrl: `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002/api/v1'}/dashboard`,
})

export async function getStats(): Promise<DashboardStats> {
  return api.get('stats').json()
}
