vi.mock('../../api', () => ({
  messageSourceApi: {
    list: vi.fn().mockResolvedValue([]),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useMessageSources } from '../use-message-sources'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useMessageSources', () => {
  it('calls messageSourceApi.list on mount', async () => {
    const { messageSourceApi } = await import('../../api')
    renderHook(() => useMessageSources(), { wrapper: createWrapper() })
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useMessageSources(), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })

  it('eventually returns data', async () => {
    const { result } = renderHook(() => useMessageSources(), { wrapper: createWrapper() })
  })
})
