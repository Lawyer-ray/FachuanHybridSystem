import { useQuery } from '@tanstack/react-query'
import { createFeatureApiClient } from '@/lib/api'
import type { Lawyer } from '../types'

const api = createFeatureApiClient('organization')

export function useLawyers() {
  return useQuery<Lawyer[]>({
    queryKey: ['lawyers'],
    queryFn: () => api.get('lawyers').json<Lawyer[]>(),
    staleTime: 10 * 60 * 1000,
  })
}
