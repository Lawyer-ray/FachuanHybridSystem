vi.mock('../../api', () => ({
  caseApi: {
    createAssignment: vi.fn().mockResolvedValue({ id: 1 }),
    deleteAssignment: vi.fn().mockResolvedValue(undefined),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useAssignmentMutations } from '../use-assignment-mutations'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useAssignmentMutations', () => {
  it('returns createAssignment and deleteAssignment', () => {
    const { result } = renderHook(() => useAssignmentMutations(1), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('createAssignment')
    expect(result.current).toHaveProperty('deleteAssignment')
  })

  it('createAssignment calls caseApi.createAssignment', async () => {
    const { caseApi } = await import('../../api')
    const { result } = renderHook(() => useAssignmentMutations(1), { wrapper: createWrapper() })
    await act(async () => { result.current.createAssignment.mutate({ case_id: 1, lawyer_id: 2 }) })
  })

  it('deleteAssignment calls caseApi.deleteAssignment', async () => {
    const { caseApi } = await import('../../api')
    const { result } = renderHook(() => useAssignmentMutations(1), { wrapper: createWrapper() })
    act(() => { result.current.deleteAssignment.mutate(5) })
    expect(result.current.deleteAssignment).toHaveProperty("isPending")
  })
})
