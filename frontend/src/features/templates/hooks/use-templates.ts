import { useQuery } from '@tanstack/react-query'
import { templateApi } from '../api'

export function useTemplates() {
  return useQuery({
    queryKey: ['templates'],
    queryFn: () => templateApi.list(),
    staleTime: 60 * 1000,
  })
}
