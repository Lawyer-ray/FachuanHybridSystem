import { useQuery } from '@tanstack/react-query'
import ky from 'ky'
import { getAccessToken } from '@/lib/token'
import type { Lawyer } from '../types'

const api = ky.create({
  prefixUrl: 'http://localhost:8002/api/v1/organization',
  hooks: { beforeRequest: [(r) => { const t = getAccessToken(); if (t) r.headers.set('Authorization', `Bearer ${t}`) }] },
})

export function useLawyers() {
  return useQuery<Lawyer[]>({
    queryKey: ['lawyers'],
    queryFn: () => api.get('lawyers').json<Lawyer[]>(),
    staleTime: 10 * 60 * 1000,
  })
}
