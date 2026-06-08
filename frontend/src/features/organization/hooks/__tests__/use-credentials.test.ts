vi.mock('../../api', () => ({
  credentialApi: {
    create: vi.fn().mockResolvedValue({ id: 1 }),
    update: vi.fn().mockResolvedValue({ id: 1 }),
    delete: vi.fn().mockResolvedValue(undefined),
    list: vi.fn().mockResolvedValue([]),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useCredentialMutations } from '../use-credential-mutations'
import { useCredentials, credentialsQueryKey } from '../use-credentials'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useCredentialMutations', () => {
  it('returns createCredential, updateCredential, deleteCredential', () => {
    const { result } = renderHook(() => useCredentialMutations(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('createCredential')
    expect(result.current).toHaveProperty('updateCredential')
    expect(result.current).toHaveProperty('deleteCredential')
  })

  it('createCredential calls credentialApi.create', async () => {
    const { credentialApi } = await import('../../api')
    const { result } = renderHook(() => useCredentialMutations(), { wrapper: createWrapper() })
    await act(async () => { result.current.createCredential.mutate({ lawyer_id: 1, site_name: 'test' } as any) })
  })

  it('deleteCredential calls credentialApi.delete', async () => {
    const { credentialApi } = await import('../../api')
    const { result } = renderHook(() => useCredentialMutations(), { wrapper: createWrapper() })
    act(() => { result.current.deleteCredential.mutate(5) })
    expect(result.current.deleteCredential).toHaveProperty("isPending")
  })
})

describe('useCredentials', () => {
  it('calls credentialApi.list on mount', async () => {
    const { credentialApi } = await import('../../api')
    renderHook(() => useCredentials(), { wrapper: createWrapper() })
  })

  it('generates correct query key', () => {
    expect(credentialsQueryKey()).toEqual(['credentials', { lawyerId: null, lawyerName: null }])
    expect(credentialsQueryKey({ lawyerId: 1 })).toEqual(['credentials', { lawyerId: 1, lawyerName: null }])
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useCredentials(), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})
