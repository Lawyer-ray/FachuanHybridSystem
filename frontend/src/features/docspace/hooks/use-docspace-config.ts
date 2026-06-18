import { useQuery } from '@tanstack/react-query'
import { docspaceApi } from '../api'

export function useDocSpaceConfig() {
  return useQuery({
    queryKey: ['docspace', 'config'],
    queryFn: docspaceApi.getConfig,
    staleTime: 5 * 60 * 1000,
  })
}
