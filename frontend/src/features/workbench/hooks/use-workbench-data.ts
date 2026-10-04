import { useMemo } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { useDebouncedValue } from '@/hooks/use-debounced-value'
import { useToday } from '@/hooks/use-today'
import { errMessage } from '@/lib/errors'
import { listContractsPage, listLawyers } from '../api'
import { buildDeals } from '../domain'
import type { ContractPageResponse, WorkbenchDeal, WorkbenchFilter } from '../types'

/** 本域 query key 工厂：分页合同（随筛选+页码变化）与律师各自缓存 */
export const workbenchKeys = {
  lawyers: ['workbench', 'lawyers'] as const,
  contractPage: (f: WorkbenchFilter, q: string, page: number) =>
    ['workbench', 'contracts-page', f.status, f.cat, f.fee, q, page] as const,
  contractCases: (contractId: number) => ['workbench', 'contract-cases', contractId] as const,
}

export interface WorkbenchData {
  deals: WorkbenchDeal[]
  /** 当前筛选命中的总条数（分页用） */
  total: number
  totalPages: number
  page: number
  /** 翻页/筛选请求进行中（keepPreviousData 期间旧列表仍展示） */
  fetching: boolean
  facets: ContractPageResponse | null
  /** 全库口径（lede 用）：合同总数 / 在办数 */
  totalContracts: number
  activeCount: number
  isLoading: boolean
  error: string | null
  refetch: () => void
}

/**
 * 办案主页列表数据：服务端分页（每页 50）+ facets 全库计数。
 * 筛选/搜索全部下推后端（排序后端固定「离今天最近」）；律师表独立缓存。
 * 案件明细不随列表加载——抽屉打开时按合同 ID 按需拉（useContractCases）。
 */
export function useWorkbenchData(filter: WorkbenchFilter, page: number): WorkbenchData {
  // 搜索防抖：输入停 300ms 才进 queryKey，避免逐键打后端
  const dq = useDebouncedValue(filter.q.trim(), 300)
  const pageQuery = useQuery({
    queryKey: workbenchKeys.contractPage(filter, dq, page),
    queryFn: () =>
      listContractsPage({ page, status: filter.status, cat: filter.cat, fee: filter.fee, q: dq }),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  })
  const lawyers = useQuery({ queryKey: workbenchKeys.lawyers, queryFn: listLawyers, staleTime: 60_000 })

  // useToday 跨零点/后台切回重算：整夜不关的办案页不会把「今日到期」
  // 口径冻结在昨天（旧 useMemo([]) 挂载即定格的缺陷）
  const today = useToday()

  const deals = useMemo(
    () =>
      pageQuery.data && lawyers.data ? buildDeals(pageQuery.data.items, lawyers.data, today) : [],
    [pageQuery.data, lawyers.data, today],
  )

  const statusCounts = pageQuery.data?.status_counts ?? {}
  const totalContracts = Object.values(statusCounts).reduce((a, b) => a + b, 0)
  const total = pageQuery.data?.total ?? 0
  const pageSize = pageQuery.data?.page_size ?? 50

  const error = pageQuery.error || lawyers.error
  return {
    deals,
    total,
    totalPages: Math.max(1, Math.ceil(total / pageSize)),
    page: pageQuery.data?.page ?? page,
    fetching: pageQuery.isFetching,
    facets: pageQuery.data ?? null,
    totalContracts,
    activeCount: statusCounts['active'] ?? 0,
    isLoading: pageQuery.isPending || lawyers.isPending,
    error: error ? errMessage(error, '办案数据加载失败') : null,
    refetch: () => {
      void pageQuery.refetch()
      void lawyers.refetch()
    },
  }
}
