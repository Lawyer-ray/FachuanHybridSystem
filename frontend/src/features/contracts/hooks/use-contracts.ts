import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { contractApi } from '../api'
import type { Contract, ContractListParams, PaginatedResponse } from '../types'

export const contractsQueryKey = (params: ContractListParams) => [
  'contracts', { caseType: params.case_type ?? null, status: params.status ?? null },
] as const

export function useContracts(params: ContractListParams = {}) {
  const { page = 1, page_size = 20, case_type, status } = params

  return useQuery<PaginatedResponse<Contract>>({
    queryKey: [...contractsQueryKey(params), page, page_size],
    queryFn: async () => {
      const all = await contractApi.list({ case_type, status })
      const total = all.length
      const totalPages = Math.ceil(total / page_size) || 1
      const start = (page - 1) * page_size
      return {
        items: all.slice(start, start + page_size),
        total,
        page,
        page_size,
        total_pages: totalPages,
      }
    },
    placeholderData: keepPreviousData,
    staleTime: 5 * 60 * 1000,
  })
}
