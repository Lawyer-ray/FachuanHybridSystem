import { useMutation, useQueryClient } from '@tanstack/react-query'

import { caseApi } from '../api'
import type { CaseParty } from '../types'
import { caseQueryKey } from './use-case'

interface CreatePartyParams {
  case_id: number
  client_id: number
  legal_status?: string
}

interface UpdatePartyParams {
  id: number | string
  data: { case_id?: number; client_id?: number; legal_status?: string }
}

export function usePartyMutations(caseId: number | string) {
  const queryClient = useQueryClient()

  const invalidateCase = () => {
    queryClient.invalidateQueries({ queryKey: caseQueryKey(caseId) })
  }

  const createParty = useMutation<CaseParty, Error, CreatePartyParams>({
    mutationFn: (data) => caseApi.createParty(data),
    onSuccess: invalidateCase,
  })

  const updateParty = useMutation<CaseParty, Error, UpdatePartyParams>({
    mutationFn: ({ id, data }) => caseApi.updateParty(id, data),
    onSuccess: invalidateCase,
  })

  const deleteParty = useMutation<void, Error, number | string>({
    mutationFn: (id) => caseApi.deleteParty(id),
    onSuccess: invalidateCase,
  })

  return { createParty, updateParty, deleteParty }
}

export default usePartyMutations
