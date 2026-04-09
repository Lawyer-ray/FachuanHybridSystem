import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { contractApi } from '../api'
import type { FolderBinding, FolderBrowseResponse } from '../types'

export function useFolderBinding(contractId: number) {
  const qc = useQueryClient()
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ['folder-binding', contractId] })
    qc.invalidateQueries({ queryKey: ['contract', String(contractId)] })
  }

  const binding = useQuery<FolderBinding | null>({
    queryKey: ['folder-binding', contractId],
    queryFn: () => contractApi.getBinding(contractId),
    staleTime: 5 * 60 * 1000,
  })

  const createBinding = useMutation({
    mutationFn: (path: string) => contractApi.createBinding(contractId, path),
    onSuccess: invalidate,
  })

  const deleteBinding = useMutation({
    mutationFn: () => contractApi.deleteBinding(contractId),
    onSuccess: invalidate,
  })

  return { binding, createBinding, deleteBinding }
}

export function useFolderBrowse(path?: string) {
  return useQuery<FolderBrowseResponse>({
    queryKey: ['folder-browse', path ?? ''],
    queryFn: () => contractApi.browseFolders(path),
    enabled: true,
    staleTime: 30 * 1000,
  })
}
