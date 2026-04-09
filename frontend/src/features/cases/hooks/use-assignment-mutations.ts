import { useMutation, useQueryClient } from '@tanstack/react-query'

import { caseApi } from '../api'
import type { CaseAssignment } from '../types'
import { caseQueryKey } from './use-case'

interface CreateAssignmentParams {
  case_id: number
  lawyer_id: number
}

export function useAssignmentMutations(caseId: number | string) {
  const queryClient = useQueryClient()

  const invalidateCase = () => {
    queryClient.invalidateQueries({ queryKey: caseQueryKey(caseId) })
  }

  const createAssignment = useMutation<CaseAssignment, Error, CreateAssignmentParams>({
    mutationFn: (data) => caseApi.createAssignment(data),
    onSuccess: invalidateCase,
  })

  const deleteAssignment = useMutation<void, Error, number | string>({
    mutationFn: (id) => caseApi.deleteAssignment(id),
    onSuccess: invalidateCase,
  })

  return { createAssignment, deleteAssignment }
}

export default useAssignmentMutations
