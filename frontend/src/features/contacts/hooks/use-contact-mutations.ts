import { useMutation, useQueryClient } from '@tanstack/react-query'

import { contactApi } from '../api'
import type { CaseContactInput } from '../types'

export function useContactMutations(caseId: number | string) {
  const queryClient = useQueryClient()

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['case-contacts', caseId] })
    queryClient.invalidateQueries({ queryKey: ['case', caseId] })
  }

  const createContact = useMutation({
    mutationFn: (data: CaseContactInput) => contactApi.create(data),
    onSuccess: invalidate,
  })

  const updateContact = useMutation({
    mutationFn: ({ id, data }: { id: number | string; data: Partial<CaseContactInput> }) =>
      contactApi.update(id, data),
    onSuccess: invalidate,
  })

  const deleteContact = useMutation({
    mutationFn: (id: number | string) => contactApi.delete(id),
    onSuccess: invalidate,
  })

  return { createContact, updateContact, deleteContact }
}
