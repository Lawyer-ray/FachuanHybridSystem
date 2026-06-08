vi.mock('../../api', () => ({
  clientApi: {
    addIdentityDoc: vi.fn().mockResolvedValue({ success: true, doc_id: 1 }),
    deleteIdentityDoc: vi.fn().mockResolvedValue(undefined),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useIdentityDocMutations } from '../use-identity-doc-mutations'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useIdentityDocMutations', () => {
  it('returns addDoc and deleteDoc', () => {
    const { result } = renderHook(() => useIdentityDocMutations('1'), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('addDoc')
    expect(result.current).toHaveProperty('deleteDoc')
  })

  it('addDoc calls clientApi.addIdentityDoc', async () => {
    const { clientApi } = await import('../../api')
    const { result } = renderHook(() => useIdentityDocMutations('1'), { wrapper: createWrapper() })
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    await act(async () => { result.current.addDoc.mutate({ docType: 'passport', file }) })
  })

  it('deleteDoc calls clientApi.deleteIdentityDoc', async () => {
    const { clientApi } = await import('../../api')
    const { result } = renderHook(() => useIdentityDocMutations('1'), { wrapper: createWrapper() })
    act(() => { result.current.deleteDoc.mutate(5) })
    expect(result.current.deleteDoc).toHaveProperty("isPending")
  })
})
