import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import React from 'react'
import { useAuthorityMutations } from '../use-authority-mutations'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useAuthorityMutations', () => {
  it('returns createAuthority, updateAuthority, deleteAuthority', () => {
    const { result } = renderHook(() => useAuthorityMutations(1), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('createAuthority')
    expect(result.current).toHaveProperty('updateAuthority')
    expect(result.current).toHaveProperty('deleteAuthority')
  })

  it('each mutation has mutate function', () => {
    const { result } = renderHook(() => useAuthorityMutations(1), { wrapper: createWrapper() })
    expect(typeof result.current.createAuthority.mutate).toBe('function')
    expect(typeof result.current.updateAuthority.mutate).toBe('function')
    expect(typeof result.current.deleteAuthority.mutate).toBe('function')
  })

  it('createAuthority throws placeholder error', async () => {
    const { result } = renderHook(() => useAuthorityMutations(1), { wrapper: createWrapper() })
    await expect(
      result.current.createAuthority.mutateAsync({ name: 'test' })
    ).rejects.toThrow('Authority creation is handled through case full create')
  })
})
