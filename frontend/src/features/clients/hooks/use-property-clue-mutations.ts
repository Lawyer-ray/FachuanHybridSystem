import { useMutation, useQueryClient } from '@tanstack/react-query'
import { clientApi } from '../api'
import type { PropertyClue, PropertyClueAttachment, PropertyClueInput } from '../types'
import { propertyCluesQueryKey } from './use-property-clues'

export function usePropertyClueMutations(clientId: number) {
  const qc = useQueryClient()
  const invalidate = () => qc.invalidateQueries({ queryKey: propertyCluesQueryKey(clientId) })

  const createClue = useMutation<PropertyClue, Error, PropertyClueInput>({
    mutationFn: (data) => clientApi.createPropertyClue(clientId, data),
    onSuccess: invalidate,
  })

  const updateClue = useMutation<PropertyClue, Error, { clueId: number; data: Partial<PropertyClueInput> }>({
    mutationFn: ({ clueId, data }) => clientApi.updatePropertyClue(clueId, data),
    onSuccess: invalidate,
  })

  const deleteClue = useMutation<void, Error, number>({
    mutationFn: (clueId) => clientApi.deletePropertyClue(clueId),
    onSuccess: invalidate,
  })

  const uploadAttachment = useMutation<PropertyClueAttachment, Error, { clueId: number; file: File }>({
    mutationFn: ({ clueId, file }) => clientApi.uploadClueAttachment(clueId, file),
    onSuccess: invalidate,
  })

  const deleteAttachment = useMutation<void, Error, number>({
    mutationFn: (attachmentId) => clientApi.deleteClueAttachment(attachmentId),
    onSuccess: invalidate,
  })

  return { createClue, updateClue, deleteClue, uploadAttachment, deleteAttachment }
}
