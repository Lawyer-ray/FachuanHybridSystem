import { useMemo } from 'react'
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'

import { useDebouncedValue } from '@/hooks/use-debounced-value'
import { useToday } from '@/hooks/use-today'
import { errMessage } from '@/lib/errors'
import { listContractsPage, listLawyers } from '../api'
import { buildDeals } from '../domain'
import type { ContractPageResponse, WorkbenchDeal, WorkbenchFilter } from '../types'

/** 本域 query key 工厂：分页合同（随筛选+页码变化）与律师各自缓存；详情页的单合同与逐案提醒另起键 */
export const workbenchKeys = {
  lawyers: ['workbench', 'lawyers'] as const,
  contractPage: (f: WorkbenchFilter, q: string, page: number) =>
    ['workbench', 'contracts-page', f.status, f.cat, f.fee, q, page] as const,
  contractCases: (contractId: number) => ['workbench', 'contract-cases', contractId] as const,
  contract: (contractId: number) => ['workbench', 'contract', contractId] as const,
  /** 案件直挂提醒按「该合同下的案件 id 集合」缓存：案件增减即换键重拉 */
  caseReminders: (contractId: number, caseIds: number[]) =>
    ['workbench', 'case-reminders', contractId, caseIds.join(',')] as const,
  /** 案件文件夹绑定（详情页判断可否切「文件夹视图」；null = 未绑定） */
  caseFolderBinding: (caseId: number) => ['workbench', 'case-folder-binding', caseId] as const,
  /** 绑定文件夹某一层子项（kind 区分案件/合同；subpath 变即换键下钻；invalidate 用 base 前缀） */
  folderEntries: (kind: 'case' | 'contract', ownerId: number) =>
    ['workbench', kind + '-folder-entries', ownerId] as const,
  folderEntriesItem: (kind: 'case' | 'contract', ownerId: number, subpath: string) =>
    ['workbench', kind + '-folder-entries', ownerId, subpath] as const,
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
  const queryClient = useQueryClient()
  // 搜索防抖：输入停 300ms 才进 queryKey，避免逐键打后端
  const dq = useDebouncedValue(filter.q.trim(), 300)
  // facets（状态/类目/收费计数）是**全库口径**，与页码无关：只在第 1 页拉，
  // 翻页传 include_facets=false 跳过后端那 4 次全表聚合。第 1 页的结果同时被
  // 后面所有页复用（见 facets 变量），切筛选条件会换 queryKey 重新拉。
  const pageQuery = useQuery({
    queryKey: workbenchKeys.contractPage(filter, dq, page),
    queryFn: () =>
      listContractsPage({
        page,
        status: filter.status,
        cat: filter.cat,
        fee: filter.fee,
        q: dq,
        includeFacets: page === 1,
      }),
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  })
  const lawyers = useQuery({ queryKey: workbenchKeys.lawyers, queryFn: listLawyers, staleTime: 60_000 })

  // useToday 跨零点/后台切回重算：整夜不关的办案页不会把「今日到期」
  // 口径冻结在昨天（旧 useMemo([]) 挂载即定格的缺陷）
  const today = useToday()

  // 不把律师表当列表的前置条件：buildDeals 的姓名取 assignment 自带的
  // lawyer_name（首屏必有），律师表只补 phone/license/firm——晚到只会让这三列
  // 从空变成有值，不必让整张列表陪它等。此前 && lawyers.data 让首屏同时等两个
  // 请求（其中一个是 500 人全量），是 /projects 首屏慢的主因。
  const deals = useMemo(
    () => (pageQuery.data ? buildDeals(pageQuery.data.items, lawyers.data ?? [], today) : []),
    [pageQuery.data, lawyers.data, today],
  )

  // facets 只由第 1 页产生（page===1 时 includeFacets=true）。翻页后从 React Query
  // 缓存里读同一筛选条件下的第 1 页结果，chips 计数才不会随翻页归零；缓存由
  // 上方的 pageQuery 自己写入，无需额外状态。
  const facetKey = queryClient.getQueryData<ContractPageResponse>(workbenchKeys.contractPage(filter, dq, 1))
  const facetData = page === 1 ? pageQuery.data : facetKey
  const statusCounts = facetData?.status_counts ?? {}
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
    facets: facetData ?? null,
    totalContracts,
    activeCount: statusCounts['active'] ?? 0,
    // 只看合同页请求：律师表（500 人全量）与列表渲染无强依赖，不该阻塞首屏
    isLoading: pageQuery.isPending,
    error: error ? errMessage(error, '办案数据加载失败') : null,
    refetch: () => {
      void pageQuery.refetch()
      void lawyers.refetch()
    },
  }
}
