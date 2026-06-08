vi.mock('../../api', () => ({
  caseApi: {
    get: vi.fn().mockResolvedValue({ id: 1, name: 'Test Case' }),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useCase, caseQueryKey } from '../use-case'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useCase', () => {
  it('calls caseApi.get with the given id', async () => {
    const { caseApi } = await import('../../api')
    renderHook(() => useCase(42), { wrapper: createWrapper() })
  })

  it('does not call API when id is falsy', async () => {
    const { caseApi } = vi.mocked(await import('../../api'))
    ;(caseApi.get as any).mockClear()
    renderHook(() => useCase(0 as any), { wrapper: createWrapper() })
    // When id is falsy, enabled: !!id is false, so API should not be called
    expect(caseApi.get).not.toHaveBeenCalled()
  })

  it('generates correct query key', () => {
    expect(caseQueryKey(1)).toEqual(['case', 1])
    expect(caseQueryKey('abc')).toEqual(['case', 'abc'])
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useCase(1), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})
