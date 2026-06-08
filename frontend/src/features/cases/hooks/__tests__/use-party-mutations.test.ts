vi.mock('../../api', () => ({
  caseApi: {
    createParty: vi.fn().mockResolvedValue({ id: 1 }),
    updateParty: vi.fn().mockResolvedValue({ id: 1 }),
    deleteParty: vi.fn().mockResolvedValue(undefined),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { usePartyMutations } from '../use-party-mutations'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('usePartyMutations', () => {
  it('returns createParty, updateParty, deleteParty', () => {
    const { result } = renderHook(() => usePartyMutations(1), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('createParty')
    expect(result.current).toHaveProperty('updateParty')
    expect(result.current).toHaveProperty('deleteParty')
  })

  it('createParty calls caseApi.createParty', async () => {
    const { caseApi } = await import('../../api')
    const { result } = renderHook(() => usePartyMutations(1), { wrapper: createWrapper() })
    await act(async () => { result.current.createParty.mutate({ case_id: 1, client_id: 2 }) })
  })

  it('deleteParty calls caseApi.deleteParty', async () => {
    const { caseApi } = await import('../../api')
    const { result } = renderHook(() => usePartyMutations(1), { wrapper: createWrapper() })
    act(() => { result.current.deleteParty.mutate(5) })
    expect(result.current.deleteParty).toHaveProperty("isPending")
  })
})
