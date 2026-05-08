import { createFeatureApiClient } from '@/lib/api'
import type { DashboardStats } from './types'

const api = createFeatureApiClient('dashboard')

export async function getStats(): Promise<DashboardStats> {
  return api.get('stats').json()
}
