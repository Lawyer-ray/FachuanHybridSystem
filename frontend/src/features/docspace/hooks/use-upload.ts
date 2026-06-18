import { useMutation, useQueryClient } from '@tanstack/react-query'
import { docspaceApi } from '../api'
import type { DocSpaceUploadResult } from '../types'

export function useUploadDocSpace() {
  const qc = useQueryClient()
  return useMutation<DocSpaceUploadResult, Error, { file: File; folderId?: number }>({
    mutationFn: ({ file, folderId }) => docspaceApi.upload(file, folderId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['docspace', 'documents'] }),
  })
}

export function useCreateDocSpaceDocument() {
  const qc = useQueryClient()
  return useMutation<DocSpaceUploadResult, Error, string | undefined>({
    mutationFn: (title) => docspaceApi.createDocument(title),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['docspace', 'documents'] }),
  })
}
