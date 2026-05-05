import { useQuery } from '@tanstack/react-query'

import { caseApi } from '../api'
import type { CaseAccessGrant } from '../types'

export function useAccessGrants(caseId: number | string | undefined) {
  return useQuery<CaseAccessGrant[]>({
    queryKey: ['cases', caseId, 'grants'],
    queryFn: () => caseApi.listGrants(caseId!),
    enabled: !!caseId,
  })
}

export default useAccessGrants
