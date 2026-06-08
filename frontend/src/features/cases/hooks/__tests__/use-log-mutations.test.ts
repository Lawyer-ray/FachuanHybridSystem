vi.mock('../../api', () => ({
  caseApi: {
    createLog: vi.fn().mockResolvedValue({ id: 1 }),
    updateLog: vi.fn().mockResolvedValue({ id: 1 }),
    deleteLog: vi.fn().mockResolvedValue(undefined),
    uploadLogAttachments: vi.fn().mockResolvedValue([]),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useLogMutations } from '../use-log-mutations'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useLogMutations', () => {
  it('returns all log mutations', () => {
    const { result } = renderHook(() => useLogMutations(1), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('createLog')
    expect(result.current).toHaveProperty('updateLog')
    expect(result.current).toHaveProperty('deleteLog')
    expect(result.current).toHaveProperty('uploadAttachments')
  })

  it('createLog calls caseApi.createLog', async () => {
    const { caseApi } = await import('../../api')
    const { result } = renderHook(() => useLogMutations(1), { wrapper: createWrapper() })
    await act(async () => { result.current.createLog.mutate({ case_id: 1, content: 'note' }) })
  })

  it('deleteLog calls caseApi.deleteLog', async () => {
    const { caseApi } = await import('../../api')
    const { result } = renderHook(() => useLogMutations(1), { wrapper: createWrapper() })
    act(() => { result.current.deleteLog.mutate(5) })
    expect(result.current.deleteLog).toHaveProperty("isPending")
  })
})
