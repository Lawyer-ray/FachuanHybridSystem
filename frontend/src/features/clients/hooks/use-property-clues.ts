import { useQuery } from '@tanstack/react-query'
import { clientApi } from '../api'
import type { PropertyClue } from '../types'

export const propertyCluesQueryKey = (clientId: number) =>
  ['property-clues', clientId] as const

export function usePropertyClues(clientId: number) {
  return useQuery<PropertyClue[]>({
    queryKey: propertyCluesQueryKey(clientId),
    queryFn: () => clientApi.listPropertyClues(clientId),
    enabled: !!clientId,
    staleTime: 5 * 60 * 1000,
  })
}
