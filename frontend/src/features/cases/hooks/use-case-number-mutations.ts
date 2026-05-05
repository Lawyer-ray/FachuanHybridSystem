import { useMutation, useQueryClient } from '@tanstack/react-query'

import { caseApi } from '../api'
import type { CaseNumber } from '../types'
import { caseQueryKey } from './use-case'

interface CreateCaseNumberParams {
  case_id: number
  number: string
  remarks?: string
  document_name?: string
  is_active?: boolean
  execution_cutoff_date?: string | null
  execution_paid_amount?: number
  execution_use_deduction_order?: boolean
  execution_year_days?: number | null
  execution_date_inclusion?: string | null
  execution_manual_text?: string | null
}

interface UpdateCaseNumberParams {
  id: number | string
  data: { number?: string; remarks?: string; document_name?: string; is_active?: boolean; execution_cutoff_date?: string | null; execution_paid_amount?: number; execution_use_deduction_order?: boolean; execution_year_days?: number | null; execution_date_inclusion?: string | null; execution_manual_text?: string | null }
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
