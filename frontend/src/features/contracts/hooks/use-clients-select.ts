import { useQuery } from '@tanstack/react-query'
import ky from 'ky'
import { getAccessToken } from '@/lib/token'

interface ClientOption { id: number; name: string; client_type: string; client_type_label: string; is_our_client: boolean }

const api = ky.create({
  prefixUrl: 'http://localhost:8002/api/v1/client',
  hooks: { beforeRequest: [(r) => { const t = getAccessToken(); if (t) r.headers.set('Authorization', `Bearer ${t}`) }] },
})

export function useClientsSelect() {
  return useQuery<ClientOption[]>({
    queryKey: ['clients-select'],
    queryFn: () => api.get('clients').json<ClientOption[]>(),
    staleTime: 10 * 60 * 1000,
  })
}
