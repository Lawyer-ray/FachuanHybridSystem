import { useQuery } from '@tanstack/react-query'

import { contactApi } from '../api'
import type { CaseContactSearchResult } from '../types'

export function useContactSearch(params: {
  q?: string
  court?: string
  role?: string
}) {
  return useQuery<CaseContactSearchResult[]>({
    queryKey: ['contact-search', params],
    queryFn: () => contactApi.search(params),
    enabled: !!(params.q || params.court || params.role),
    staleTime: 2 * 60 * 1000,
  })
}
