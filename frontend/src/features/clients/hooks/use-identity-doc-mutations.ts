import { useMutation, useQueryClient } from '@tanstack/react-query'
import { clientApi } from '../api'
import { clientQueryKey } from './use-client'

export function useIdentityDocMutations(clientId: string) {
  const qc = useQueryClient()
  const invalidate = () => qc.invalidateQueries({ queryKey: clientQueryKey(clientId) })

  const addDoc = useMutation<{ success: boolean; doc_id: number }, Error, { docType: string; file: File }>({
    mutationFn: ({ docType, file }) => clientApi.addIdentityDoc(Number(clientId), docType, file),
    onSuccess: invalidate,
  })

  const deleteDoc = useMutation<void, Error, number>({
    mutationFn: (docId) => clientApi.deleteIdentityDoc(docId),
    onSuccess: invalidate,
  })

  return { addDoc, deleteDoc }
}
