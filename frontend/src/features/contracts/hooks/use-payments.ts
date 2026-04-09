import { useQuery } from '@tanstack/react-query'
import { contractApi } from '../api'
import type { ContractPayment } from '../types'

export function usePayments(contractId: number) {
  return useQuery<ContractPayment[]>({
    queryKey: ['payments', contractId],
    queryFn: () => contractApi.listPayments({ contract_id: contractId }),
    staleTime: 5 * 60 * 1000,
  })
}
