import { useMutation, useQueryClient } from '@tanstack/react-query'

import { caseApi } from '../api'
import type { CaseNumber } from '../types'
import { caseQueryKey } from './use-case'

interface CreateCaseNumberParams {
  case_id: number
  number: string
  remarks?: string
}

interface UpdateCaseNumberParams {
  id: number | string
  data: { number?: string; remarks?: string }
}

export function useCaseNumberMutations(caseId: number | string) {
  const queryClient = useQueryClient()

  const invalidateCase = () => {
    queryClient.invalidateQueries({ queryKey: caseQueryKey(caseId) })
  }

  const createCaseNumber = useMutation<CaseNumber, Error, CreateCaseNumberParams>({
    mutationFn: (data) => caseApi.createCaseNumber(data),
    onSuccess: invalidateCase,
  })

  const updateCaseNumber = useMutation<CaseNumber, Error, UpdateCaseNumberParams>({
    mutationFn: ({ id, data }) => caseApi.updateCaseNumber(id, data),
    onSuccess: invalidateCase,
  })

  const deleteCaseNumber = useMutation<void, Error, number | string>({
    mutationFn: (id) => caseApi.deleteCaseNumber(id),
    onSuccess: invalidateCase,
  })

  return { createCaseNumber, updateCaseNumber, deleteCaseNumber }
}

export default useCaseNumberMutations
