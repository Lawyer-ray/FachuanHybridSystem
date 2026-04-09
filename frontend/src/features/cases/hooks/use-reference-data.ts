import { useQuery, useMutation } from '@tanstack/react-query'

import { caseApi } from '../api'
import type { CauseItem, CauseTreeNode, CourtItem, FeeCalculationRequest, FeeCalculationResponse } from '../types'

export function useCauseSearch(search: string, caseType?: string) {
  return useQuery<CauseItem[]>({
    queryKey: ['causes', 'search', search, caseType],
    queryFn: () => caseApi.searchCauses(search, caseType),
    enabled: search.length >= 1,
    staleTime: 5 * 60 * 1000,
  })
}

export function useCausesTree(parentId?: number) {
  return useQuery<CauseTreeNode[]>({
    queryKey: ['causes', 'tree', parentId],
    queryFn: () => caseApi.getCausesTree(parentId),
    staleTime: 10 * 60 * 1000,
  })
}

export function useCourtSearch(search: string) {
  return useQuery<CourtItem[]>({
    queryKey: ['courts', 'search', search],
    queryFn: () => caseApi.searchCourts(search),
    enabled: search.length >= 1,
    staleTime: 5 * 60 * 1000,
  })
}

export function useCalculateFee() {
  return useMutation<FeeCalculationResponse, Error, FeeCalculationRequest>({
    mutationFn: (data) => caseApi.calculateFee(data),
  })
}

export default useCauseSearch
