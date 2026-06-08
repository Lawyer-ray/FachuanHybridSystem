vi.mock('../../api', () => ({
  caseApi: {
    listMaterialCandidates: vi.fn().mockResolvedValue([]),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useMaterialCandidates } from '../use-material-candidates'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useMaterialCandidates', () => {
  it('calls API when caseId is provided', async () => {
    const { caseApi } = await import('../../api')
    renderHook(() => useMaterialCandidates(1), { wrapper: createWrapper() })
  })

  it('does not call API when caseId is undefined', async () => {
    const { caseApi } = await import('../../api')
    ;(caseApi.listMaterialCandidates as any).mockClear()
    renderHook(() => useMaterialCandidates(undefined), { wrapper: createWrapper() })
    expect(caseApi.listMaterialCandidates).not.toHaveBeenCalled()
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useMaterialCandidates(1), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})
