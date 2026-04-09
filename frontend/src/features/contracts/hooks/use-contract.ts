import { useQuery } from '@tanstack/react-query'
import { contractApi } from '../api'
import type { Contract } from '../types'

export const contractQueryKey = (id: string | number) => ['contract', id] as const

export function useContract(id: string) {
  return useQuery<Contract>({
    queryKey: contractQueryKey(id),
    queryFn: () => contractApi.get(id),
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  })
}
