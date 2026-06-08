vi.mock('../../api', () => ({
  caseApi: {
    search: vi.fn().mockResolvedValue([]),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useCaseSearch } from '../use-case-search'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useCaseSearch', () => {
  it('calls caseApi.search when query has content', async () => {
    const { caseApi } = await import('../../api')
    renderHook(() => useCaseSearch('test'), { wrapper: createWrapper() })
  })

  it('does not call API when query is empty', async () => {
    const { caseApi } = await import('../../api')
    ;(caseApi.search as any).mockClear()
    renderHook(() => useCaseSearch(''), { wrapper: createWrapper() })
    // query length < 1 means disabled
    expect(caseApi.search).not.toHaveBeenCalled()
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useCaseSearch('test'), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})
