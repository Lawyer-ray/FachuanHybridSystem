import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import { errMessage } from '@/lib/errors'
import { listContracts, listLawyers } from '../api'
import { buildDeals } from '../domain'
import type { WorkbenchDeal } from '../types'

/** 本域 query key 工厂：列表数据与按需案件各自缓存 */
export const workbenchKeys = {
  contracts: ['workbench', 'contracts'] as const,
  lawyers: ['workbench', 'lawyers'] as const,
  contractCases: (contractId: number) => ['workbench', 'contract-cases', contractId] as const,
}

/**
 * 办案主页列表数据：合同（slim）× 律师两接口并行。
 * 案件明细不随列表加载——打开抽屉时按合同 ID 按需拉（useContractCases）。
 * 后端契约就是前端客户端筛选/分页（合同 ~150 条），故 staleTime 放宽到 60s。
 */
export function useWorkbenchData(): {
  deals: WorkbenchDeal[]
  isLoading: boolean
  error: string | null
  refetch: () => void
} {
  const contracts = useQuery({ queryKey: workbenchKeys.contracts, queryFn: listContracts, staleTime: 60_000 })
  const lawyers = useQuery({ queryKey: workbenchKeys.lawyers, queryFn: listLawyers, staleTime: 60_000 })

  const today = useMemo(() => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    return d
  }, [])

  const deals = useMemo(
    () => (contracts.data && lawyers.data ? buildDeals(contracts.data, lawyers.data, today) : []),
    [contracts.data, lawyers.data, today],
  )

  const error = contracts.error || lawyers.error
  return {
    deals,
    isLoading: contracts.isPending || lawyers.isPending,
    error: error ? errMessage(error, '办案数据加载失败') : null,
    refetch: () => {
      void contracts.refetch()
      void lawyers.refetch()
    },
  }
}
