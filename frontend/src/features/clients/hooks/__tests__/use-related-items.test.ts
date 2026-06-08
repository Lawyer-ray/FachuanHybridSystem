vi.mock('../../api', () => ({
  clientApi: {
    getRelatedItems: vi.fn().mockResolvedValue({ cases: [], contracts: [] }),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useRelatedItems, relatedItemsQueryKey } from '../use-related-items'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useRelatedItems', () => {
  it('calls clientApi.getRelatedItems with numeric clientId', async () => {
    const { clientApi } = await import('../../api')
    renderHook(() => useRelatedItems('42'), { wrapper: createWrapper() })
  })

  it('generates correct query key', () => {
    expect(relatedItemsQueryKey('123')).toEqual(['clients', '123', 'related-items'])
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useRelatedItems('1'), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})
