import { useQuery } from '@tanstack/react-query'
import { inboxApi } from '../api'
import type { InboxMessageDetail } from '../types'

export function useInboxMessage(id: number | string | undefined) {
  return useQuery<InboxMessageDetail>({
    queryKey: ['inbox-message', id],
    queryFn: () => inboxApi.get(id!),
    enabled: !!id,
  })
}
