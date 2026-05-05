import { useQuery } from '@tanstack/react-query'

import { caseApi } from '../api'
import type { MaterialBindCandidate } from '../types'

export function useMaterialCandidates(caseId: number | string | undefined) {
  return useQuery<MaterialBindCandidate[]>({
    queryKey: ['cases', caseId, 'materials'],
    queryFn: () => caseApi.listMaterialCandidates(caseId!),
    enabled: !!caseId,
  })
}

export default useMaterialCandidates
