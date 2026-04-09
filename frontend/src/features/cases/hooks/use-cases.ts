import { useQuery, keepPreviousData } from '@tanstack/react-query'

import { caseApi } from '../api'
import type { Case, CaseListParams } from '../types'

export const casesQueryKey = (params?: CaseListParams) => ['cases', params ?? {}] as const

export function useCases(params?: CaseListParams) {
  return useQuery<Case[]>({
    queryKey: casesQueryKey(params),
    queryFn: () => caseApi.list(params),
    placeholderData: keepPreviousData,
    staleTime: 5 * 60 * 1000,
  })
}

export default useCases
