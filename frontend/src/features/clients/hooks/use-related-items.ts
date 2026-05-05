import { useQuery } from '@tanstack/react-query'

import { clientApi } from '../api'
import type { RelatedItems } from '../types'

export const relatedItemsQueryKey = (clientId: string | number) =>
  ['clients', clientId, 'related-items'] as const

export function useRelatedItems(clientId: string | number) {
  return useQuery<RelatedItems>({
    queryKey: relatedItemsQueryKey(clientId),
    queryFn: () => clientApi.getRelatedItems(Number(clientId)),
    staleTime: 5 * 60 * 1000,
  })
}

export default useRelatedItems
