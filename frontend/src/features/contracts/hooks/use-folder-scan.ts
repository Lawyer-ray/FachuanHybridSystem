import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { contractApi } from '../api'
import type { FolderScanStatus, FolderScanSubfolderList, FolderScanConfirmItem } from '../types'

export function useFolderScan(contractId: number) {
  const qc = useQueryClient()

  const subfolders = useQuery<FolderScanSubfolderList>({
    queryKey: ['folder-scan-subfolders', contractId],
    queryFn: () => contractApi.listScanSubfolders(contractId),
    staleTime: 60 * 1000,
  })

  const startScan = useMutation({
    mutationFn: ({ rescan, subfolder }: { rescan?: boolean; subfolder?: string }) =>
      contractApi.startScan(contractId, rescan, subfolder),
  })

  const confirmScan = useMutation({
    mutationFn: ({ sessionId, items }: { sessionId: string; items: FolderScanConfirmItem[] }) =>
      contractApi.confirmScan(contractId, sessionId, items),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['contract', String(contractId)] })
    },
  })

  return { subfolders, startScan, confirmScan }
}

export function useScanStatus(contractId: number, sessionId: string | null) {
  return useQuery<FolderScanStatus>({
    queryKey: ['folder-scan-status', contractId, sessionId],
    queryFn: () => contractApi.getScanStatus(contractId, sessionId!),
    enabled: !!sessionId,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'running' || status === 'pending' ? 2000 : false
    },
  })
}
