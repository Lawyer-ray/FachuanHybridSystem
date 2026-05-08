import { useQuery } from '@tanstack/react-query'
import { getStats } from '../api'

export function useDashboardStats() {
  return useQuery({
    queryKey: ['dashboard-stats'],
    queryFn: getStats,
    staleTime: 60_000,
  })
}
