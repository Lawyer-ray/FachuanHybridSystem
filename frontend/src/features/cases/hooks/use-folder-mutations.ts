import { useMutation, useQueryClient } from '@tanstack/react-query'

import { caseApi } from '../api'
import type { FolderScanCandidate } from '../types'
import { caseQueryKey } from './use-case'

interface BindFolderParams {
  folder_path: string
  storage_type?: string
  storage_account_id?: number | null
}

export function useFolderMutations(caseId: number | string) {
  const queryClient = useQueryClient()

  const invalidateCase = () => {
    queryClient.invalidateQueries({ queryKey: caseQueryKey(caseId) })
    queryClient.invalidateQueries({ queryKey: ['cases', caseId, 'folder-binding'] })
  }

  const createFolderBinding = useMutation({
    mutationFn: (params: BindFolderParams) => caseApi.createFolderBinding(caseId, params),
    onSuccess: invalidateCase,
  })

  const deleteFolderBinding = useMutation({
    mutationFn: () => caseApi.deleteFolderBinding(caseId),
    onSuccess: invalidateCase,
  })

  const startFolderScan = useMutation({
    mutationFn: (options?: Record<string, unknown>) => caseApi.startFolderScan(caseId, options),
  })

  const stageScanResults = useMutation({
    mutationFn: ({ sessionId, items }: { sessionId: string; items: FolderScanCandidate[] }) =>
      caseApi.stageScanResults(caseId, sessionId, items),
    onSuccess: invalidateCase,
  })

  return { createFolderBinding, deleteFolderBinding, startFolderScan, stageScanResults }
}

export default useFolderMutations
