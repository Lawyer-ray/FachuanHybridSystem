/**
 * useClients Hook
 * 当事人列表查询 hook
 *
 * 使用 TanStack Query 实现列表查询，支持分页、搜索、筛选参数
 *
 * Requirements: 3.3, 3.4, 3.5, 9.6
 */

import { useQuery, keepPreviousData } from '@tanstack/react-query'

import { clientApi } from '../api'
import type { Client, ClientType } from '../types'

/**
 * 前端分页响应格式
 */
interface ClientListResult {
  items: Client[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

/**
 * useClients 参数接口
 */
export interface UseClientsParams {
  /** 当前页码（从 1 开始） */
  page?: number
  /** 每页数量（默认 20） */
  pageSize?: number
  /** 搜索关键词（支持姓名、手机号、身份证号） */
  search?: string
  /** 当事人类型筛选 */
  clientType?: ClientType
  /** 是否为我方当事人 */
  isOurClient?: boolean
}

/**
 * 当事人列表查询 Query Key
 */
export const clientsQueryKey = (params: UseClientsParams) => [
  'clients',
  {
    page: params.page ?? 1,
    pageSize: params.pageSize ?? 20,
    search: params.search ?? '',
    clientType: params.clientType ?? null,
    isOurClient: params.isOurClient ?? null,
  },
] as const

/**
 * 当事人列表查询 Hook
 *
 * @param params - 查询参数（分页、搜索、筛选）
 * @returns TanStack Query 结果，包含当事人列表和分页信息
 *
 * @example
 * ```tsx
 * // 基础用法
 * const { data, isLoading, error } = useClients({ page: 1 })
 *
 * // 带搜索和筛选
 * const { data } = useClients({
 *   page: 1,
 *   pageSize: 20,
 *   search: '张三',
 *   clientType: 'natural',
 * })
 * ```
 *
 * Requirements: 3.3 (搜索), 3.4 (类型筛选), 3.5 (分页), 9.6 (TanStack Query)
 */
export function useClients(params: UseClientsParams = {}) {
  const {
    page = 1,
    pageSize = 20,
    search,
    clientType,
    isOurClient,
  } = params

  return useQuery<ClientListResult>({
    queryKey: clientsQueryKey(params),
    queryFn: async () => {
      // 后端返回简单数组，前端转换为分页格式
      const clients = await clientApi.list({
        page,
        page_size: pageSize,
        search: search || undefined,
        client_type: clientType,
        is_our_client: isOurClient,
      })

      // 由于后端已经做了分页，这里直接使用返回的数据
      // 注意：后端分页逻辑在 service 层，返回的是当前页的数据
      const total = clients.length < pageSize && page === 1
        ? clients.length
        : clients.length === pageSize
          ? (page * pageSize) + 1 // 可能还有更多
          : ((page - 1) * pageSize) + clients.length

      return {
        items: clients,
        total,
        page,
        page_size: pageSize,
        total_pages: Math.ceil(total / pageSize) || 1,
      }
    },
    // 保持上一次数据，避免分页切换时闪烁
    placeholderData: keepPreviousData,
    // 5 分钟内数据视为新鲜，不会自动重新获取
    staleTime: 5 * 60 * 1000,
  })
}

export default useClients
