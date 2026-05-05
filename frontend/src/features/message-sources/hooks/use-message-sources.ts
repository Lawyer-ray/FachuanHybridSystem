import { useQuery } from '@tanstack/react-query'
import { messageSourceApi } from '../api'
import type { MessageSource } from '../types'

export function useMessageSources() {
  return useQuery<MessageSource[]>({
    queryKey: ['message-sources'],
    queryFn: () => messageSourceApi.list(),
    staleTime: 60 * 1000,
  })
}
