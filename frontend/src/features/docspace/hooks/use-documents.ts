import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { docspaceApi } from '../api'

export function useDocSpaceConfig() {
  return useQuery({
    queryKey: ['docspace', 'config'],
    queryFn: docspaceApi.getConfig,
    staleTime: 5 * 60 * 1000,
  })
}

export function useDocSpaceDocuments() {
  return useQuery({
    queryKey: ['docspace', 'documents'],
    queryFn: docspaceApi.listDocuments,
  })
}

export function useDocSpaceDocument(id: number) {
  return useQuery({
    queryKey: ['docspace', 'document', id],
    queryFn: () => docspaceApi.getDocument(id),
    enabled: !!id,
  })
}

export function useDeleteDocSpaceDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => docspaceApi.deleteDocument(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['docspace', 'documents'] }),
  })
}

export function useSyncDocSpaceDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => docspaceApi.syncDocument(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['docspace', 'documents'] }),
  })
}
