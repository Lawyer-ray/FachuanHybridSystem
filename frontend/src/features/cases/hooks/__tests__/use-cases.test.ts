vi.mock('../../api', () => ({
  caseApi: {
    list: vi.fn().mockResolvedValue([]),
    search: vi.fn().mockResolvedValue([]),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useCases, casesQueryKey } from '../use-cases'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useCases', () => {
  it('calls caseApi.list on mount', async () => {
    const { caseApi } = await import('../../api')
    renderHook(() => useCases(), { wrapper: createWrapper() })
  })

  it('passes params to caseApi.list', async () => {
    const { caseApi } = await import('../../api')
    const params = { page: 1, status: 'active' }
    renderHook(() => useCases(params), { wrapper: createWrapper() })
  })

  it('generates correct query key with params', () => {
    expect(casesQueryKey({ page: 1 })).toEqual(['cases', { page: 1 }])
    expect(casesQueryKey()).toEqual(['cases', {}])
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useCases(), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})
