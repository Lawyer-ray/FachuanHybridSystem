import { useQuery } from '@tanstack/react-query'
import { templateApi } from '../api'

export function useTemplate(id: number) {
  return useQuery({
    queryKey: ['templates', id],
    queryFn: () => templateApi.get(id),
    enabled: !!id,
  })
}
