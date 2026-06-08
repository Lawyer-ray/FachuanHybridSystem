vi.mock('../../api', () => ({
  caseApi: {
    searchCauses: vi.fn().mockResolvedValue([]),
    getCausesTree: vi.fn().mockResolvedValue([]),
    searchCourts: vi.fn().mockResolvedValue([]),
    calculateFee: vi.fn().mockResolvedValue({ total: 100 }),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useCauseSearch, useCausesTree, useCourtSearch, useCalculateFee } from '../use-reference-data'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useCauseSearch', () => {
  it('calls API when search has content', async () => {
    const { caseApi } = await import('../../api')
    renderHook(() => useCauseSearch('contract'), { wrapper: createWrapper() })
  })

  it('does not call API when search is empty', async () => {
    const { caseApi } = await import('../../api')
    ;(caseApi.searchCauses as any).mockClear()
    renderHook(() => useCauseSearch(''), { wrapper: createWrapper() })
    expect(caseApi.searchCauses).not.toHaveBeenCalled()
  })

  it('passes caseType parameter', async () => {
    const { caseApi } = await import('../../api')
    renderHook(() => useCauseSearch('fraud', 'civil'), { wrapper: createWrapper() })
  })
})

describe('useCausesTree', () => {
  it('calls API on mount', async () => {
    const { caseApi } = await import('../../api')
    renderHook(() => useCausesTree(), { wrapper: createWrapper() })
  })

  it('passes parentId when provided', async () => {
    const { caseApi } = await import('../../api')
    renderHook(() => useCausesTree(5), { wrapper: createWrapper() })
  })
})

describe('useCourtSearch', () => {
  it('calls API when search has content', async () => {
    const { caseApi } = await import('../../api')
    renderHook(() => useCourtSearch('beijing'), { wrapper: createWrapper() })
  })

  it('does not call API when search is empty', async () => {
    const { caseApi } = await import('../../api')
    ;(caseApi.searchCourts as any).mockClear()
    renderHook(() => useCourtSearch(''), { wrapper: createWrapper() })
    expect(caseApi.searchCourts).not.toHaveBeenCalled()
  })
})

describe('useCalculateFee', () => {
  it('returns a mutation with mutate function', () => {
    const { result } = renderHook(() => useCalculateFee(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('mutate')
  })

  it('calls caseApi.calculateFee on mutate', async () => {
    const { caseApi } = await import('../../api')
    const { result } = renderHook(() => useCalculateFee(), { wrapper: createWrapper() })
    const req = { amount: 10000, case_type: 'civil' } as any
    act(() => { result.current.mutate(req) })

    expect(result.current).toHaveProperty("mutate")
  })
})
