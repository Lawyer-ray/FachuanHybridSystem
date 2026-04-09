import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { inboxApi } from '../api'
import type { InboxMessage, InboxListParams } from '../types'

interface PaginatedResult {
  items: InboxMessage[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export function useInboxMessages(params: InboxListParams & { page?: number; page_size?: number } = {}) {
  const { page = 1, page_size = 20, ...filterParams } = params

  return useQuery<PaginatedResult>({
    queryKey: ['inbox-messages', filterParams, page, page_size],
    queryFn: async () => {
      const all = await inboxApi.list(filterParams)
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
    staleTime: 2 * 60 * 1000,
  })
}
