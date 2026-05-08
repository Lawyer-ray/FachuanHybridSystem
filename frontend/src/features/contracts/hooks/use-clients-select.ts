import { useQuery } from '@tanstack/react-query'
import { createFeatureApiClient } from '@/lib/api'

interface ClientOption { id: number; name: string; client_type: string; client_type_label: string; is_our_client: boolean }

const api = createFeatureApiClient('client')

export function useClientsSelect() {
  return useQuery<ClientOption[]>({
    queryKey: ['clients-select'],
    queryFn: () => api.get('clients').json<ClientOption[]>(),
    staleTime: 10 * 60 * 1000,
  })
}
