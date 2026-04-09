import { useMutation, useQueryClient } from '@tanstack/react-query'

import { caseApi } from '../api'
import type { Case, CaseInput, CaseUpdate, CaseCreateFull } from '../types'
import { caseQueryKey } from './use-case'

interface UpdateCaseParams {
  id: number | string
  data: CaseUpdate
}

export function useCaseMutations() {
  const queryClient = useQueryClient()

  const invalidateCases = () => {
    queryClient.invalidateQueries({ queryKey: ['cases'] })
  }

  const createCase = useMutation<Case, Error, CaseInput>({
    mutationFn: (data) => caseApi.create(data),
    onSuccess: invalidateCases,
  })

  const createCaseFull = useMutation({
    mutationFn: (data: CaseCreateFull) => caseApi.createFull(data),
    onSuccess: invalidateCases,
  })

  const updateCase = useMutation<Case, Error, UpdateCaseParams>({
    mutationFn: ({ id, data }) => caseApi.update(id, data),
    onSuccess: (_, { id }) => {
      invalidateCases()
      queryClient.invalidateQueries({ queryKey: caseQueryKey(id) })
    },
  })

  const deleteCase = useMutation<void, Error, number | string>({
    mutationFn: (id) => caseApi.delete(id),
    onSuccess: (_, id) => {
      invalidateCases()
      queryClient.removeQueries({ queryKey: caseQueryKey(id) })
    },
  })

  return { createCase, createCaseFull, updateCase, deleteCase }
}

export default useCaseMutations
