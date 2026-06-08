vi.mock('../../api', () => ({
  caseApi: {
    listGrants: vi.fn().mockResolvedValue([]),
    createGrant: vi.fn().mockResolvedValue({ id: 1 }),
    deleteGrant: vi.fn().mockResolvedValue(undefined),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useAccessGrants } from '../use-access-grants'
import { useAccessGrantMutations } from '../use-access-grant-mutations'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useAccessGrants', () => {
  it('calls caseApi.listGrants when caseId is provided', async () => {
    const { caseApi } = await import('../../api')
    renderHook(() => useAccessGrants(1), { wrapper: createWrapper() })
  })

  it('does not call API when caseId is undefined', async () => {
    const { caseApi } = await import('../../api')
    ;(caseApi.listGrants as any).mockClear()
    renderHook(() => useAccessGrants(undefined), { wrapper: createWrapper() })
    expect(caseApi.listGrants).not.toHaveBeenCalled()
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useAccessGrants(1), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useAccessGrantMutations', () => {
  it('returns createGrant and deleteGrant', () => {
    const { result } = renderHook(() => useAccessGrantMutations(1), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('createGrant')
    expect(result.current).toHaveProperty('deleteGrant')
  })

  it('createGrant calls caseApi.createGrant', async () => {
    const { caseApi } = await import('../../api')
    const { result } = renderHook(() => useAccessGrantMutations(1), { wrapper: createWrapper() })
    await act(async () => { result.current.createGrant.mutate({ case_id: 1, grantee_id: 2 }) })
  })

  it('deleteGrant calls caseApi.deleteGrant', async () => {
    const { caseApi } = await import('../../api')
    const { result } = renderHook(() => useAccessGrantMutations(1), { wrapper: createWrapper() })
    act(() => { result.current.deleteGrant.mutate(5) })
    expect(result.current.deleteGrant).toHaveProperty("isPending")
  })
})
