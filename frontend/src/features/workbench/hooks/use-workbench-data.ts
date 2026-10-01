import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import { errMessage } from '@/lib/errors'
import { listCases, listContracts, listLawyers } from '../api'
import { buildDeals } from '../domain'
import type { WorkbenchDeal } from '../types'

/** 本域 query key 工厂：三接口各自缓存，合并层在组件 useMemo */
export const workbenchKeys = {
  contracts: ['workbench', 'contracts'] as const,
  cases: ['workbench', 'cases'] as const,
  lawyers: ['workbench', 'lawyers'] as const,
}

/**
 * 办案主页数据：合同 × 案件 × 律师三只读接口并行拉取，全量合并成 WorkbenchDeal。
 * 后端契约就是前端客户端筛选/分页（合同 ~150 条），故 staleTime 放宽到 60s。
 */
export function useWorkbenchData(): {
  deals: WorkbenchDeal[]
  isLoading: boolean
  error: string | null
  refetch: () => void
} {
  const contracts = useQuery({ queryKey: workbenchKeys.contracts, queryFn: listContracts, staleTime: 60_000 })
  const cases = useQuery({ queryKey: workbenchKeys.cases, queryFn: listCases, staleTime: 60_000 })
  const lawyers = useQuery({ queryKey: workbenchKeys.lawyers, queryFn: listLawyers, staleTime: 60_000 })

  const today = useMemo(() => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    return d
  }, [])

  const deals = useMemo(
    () =>
      contracts.data && cases.data && lawyers.data
        ? buildDeals(contracts.data, cases.data, lawyers.data, today)
        : [],
    [contracts.data, cases.data, lawyers.data, today],
  )

  const error = contracts.error || cases.error || lawyers.error
  return {
    deals,
    isLoading: contracts.isPending || cases.isPending || lawyers.isPending,
    error: error ? errMessage(error, '办案数据加载失败') : null,
    refetch: () => {
      void contracts.refetch()
      void cases.refetch()
      void lawyers.refetch()
    },
  }
}
