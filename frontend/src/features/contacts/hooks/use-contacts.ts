import { useQuery } from '@tanstack/react-query'

import { contactApi } from '../api'
import type { CaseContact } from '../types'

export function useContacts(caseId: number | string, stage?: string) {
  return useQuery<CaseContact[]>({
    queryKey: ['case-contacts', caseId, stage],
    queryFn: () => contactApi.list(caseId, stage),
    enabled: !!caseId,
    staleTime: 5 * 60 * 1000,
  })
}
