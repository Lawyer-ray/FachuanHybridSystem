vi.mock('../../api', () => ({
  getStats: vi.fn().mockResolvedValue({ total_cases: 10 }),
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useDashboardStats } from '../use-dashboard-stats'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useDashboardStats', () => {
  it('calls getStats on mount', async () => {
    const { getStats } = await import('../../api')
    renderHook(() => useDashboardStats(), { wrapper: createWrapper() })
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useDashboardStats(), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })

  it('eventually returns data', async () => {
    const { result } = renderHook(() => useDashboardStats(), { wrapper: createWrapper() })
  })
})
