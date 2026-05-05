import { useQuery } from '@tanstack/react-query'

import { caseApi } from '../api'
import type { FolderBinding } from '../types'

export function useFolderBinding(caseId: number | string | undefined) {
  return useQuery<FolderBinding | null>({
    queryKey: ['cases', caseId, 'folder-binding'],
    queryFn: () => caseApi.getFolderBinding(caseId!),
    enabled: !!caseId,
  })
}

export default useFolderBinding
