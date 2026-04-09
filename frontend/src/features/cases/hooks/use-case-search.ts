import { useQuery } from '@tanstack/react-query'

import { caseApi } from '../api'
import type { Case } from '../types'

export function useCaseSearch(query: string) {
  return useQuery<Case[]>({
    queryKey: ['cases', 'search', query],
    queryFn: () => caseApi.search(query),
    enabled: query.length >= 1,
    staleTime: 2 * 60 * 1000,
  })
}

export default useCaseSearch
