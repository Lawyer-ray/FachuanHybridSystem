import { useMutation, useQueryClient } from '@tanstack/react-query'

import { caseApi } from '../api'
import type { CaseAccessGrant } from '../types'
import { caseQueryKey } from './use-case'

interface CreateGrantParams {
  case_id: number
  grantee_id: number
}

export function useAccessGrantMutations(caseId: number | string) {
  const queryClient = useQueryClient()

  const invalidateCase = () => {
    queryClient.invalidateQueries({ queryKey: caseQueryKey(caseId) })
  }

  const createGrant = useMutation<CaseAccessGrant, Error, CreateGrantParams>({
    mutationFn: (data) => caseApi.createGrant(data),
    onSuccess: invalidateCase,
  })

  const deleteGrant = useMutation<void, Error, number | string>({
    mutationFn: (id) => caseApi.deleteGrant(id),
    onSuccess: invalidateCase,
  })

  return { createGrant, deleteGrant }
}

export default useAccessGrantMutations
