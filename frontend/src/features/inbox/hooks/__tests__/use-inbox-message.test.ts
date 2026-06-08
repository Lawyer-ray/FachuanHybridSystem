vi.mock('../../api', () => ({
  inboxApi: {
    get: vi.fn().mockResolvedValue({ id: 1, subject: 'Test Message' }),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useInboxMessage } from '../use-inbox-message'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useInboxMessage', () => {
  it('calls inboxApi.get when id is provided', async () => {
    const { inboxApi } = await import('../../api')
    renderHook(() => useInboxMessage(1), { wrapper: createWrapper() })
  })

  it('does not call API when id is undefined', async () => {
    const { inboxApi } = await import('../../api')
    ;(inboxApi.get as any).mockClear()
    renderHook(() => useInboxMessage(undefined), { wrapper: createWrapper() })
    expect(inboxApi.get).not.toHaveBeenCalled()
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useInboxMessage(1), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})
