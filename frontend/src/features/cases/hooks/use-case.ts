import { useQuery } from '@tanstack/react-query'

import { caseApi } from '../api'
import type { Case } from '../types'

export const caseQueryKey = (id: string | number) => ['case', id] as const

export function useCase(id: string | number) {
  return useQuery<Case>({
    queryKey: caseQueryKey(id),
    queryFn: () => caseApi.get(id),
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
  })
}

export default useCase
