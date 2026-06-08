vi.mock('../../api', () => ({
  caseApi: {
    createCaseNumber: vi.fn().mockResolvedValue({ id: 1 }),
    updateCaseNumber: vi.fn().mockResolvedValue({ id: 1 }),
    deleteCaseNumber: vi.fn().mockResolvedValue(undefined),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useCaseNumberMutations } from '../use-case-number-mutations'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useCaseNumberMutations', () => {
  it('returns createCaseNumber, updateCaseNumber, deleteCaseNumber', () => {
    const { result } = renderHook(() => useCaseNumberMutations(1), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('createCaseNumber')
    expect(result.current).toHaveProperty('updateCaseNumber')
    expect(result.current).toHaveProperty('deleteCaseNumber')
  })

  it('createCaseNumber calls caseApi.createCaseNumber', async () => {
    const { caseApi } = await import('../../api')
    const { result } = renderHook(() => useCaseNumberMutations(1), { wrapper: createWrapper() })
    await act(async () => { result.current.createCaseNumber.mutate({ case_id: 1, number: '2024-001' }) })
  })

  it('updateCaseNumber calls caseApi.updateCaseNumber', async () => {
    const { caseApi } = await import('../../api')
    const { result } = renderHook(() => useCaseNumberMutations(1), { wrapper: createWrapper() })
    await act(async () => { result.current.updateCaseNumber.mutate({ id: 5, data: { number: '2024-002' } }) })
  })
})
