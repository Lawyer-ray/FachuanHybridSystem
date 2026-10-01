import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import { listCasesByContract } from '../api'
import { buildDealCases } from '../domain'
import type { DealCase } from '../types'
import { workbenchKeys } from './use-workbench-data'

/**
 * 按合同加载案件明细（抽屉「案件」节专用，打开抽屉才发请求）。
 * 同一合同 60s 内重复打开走缓存。
 */
export function useContractCases(contractId: number | null): {
  cases: DealCase[]
  isLoading: boolean
} {
  const query = useQuery({
    queryKey: workbenchKeys.contractCases(contractId ?? 0),
    queryFn: () => listCasesByContract(contractId as number),
    enabled: contractId != null,
    staleTime: 60_000,
  })

  const today = useMemo(() => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    return d
  }, [])

  const cases = useMemo(
    () => (query.data ? buildDealCases(query.data, today) : []),
    [query.data, today],
  )
  return { cases, isLoading: contractId != null && query.isPending }
}
