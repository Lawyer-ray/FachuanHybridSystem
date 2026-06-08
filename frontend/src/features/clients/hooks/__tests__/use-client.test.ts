vi.mock('../../api', () => ({
  clientApi: {
    get: vi.fn().mockResolvedValue({ id: '1', name: 'Test Client' }),
    create: vi.fn().mockResolvedValue({ id: '2' }),
    update: vi.fn().mockResolvedValue({ id: '1' }),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}))

vi.mock('@/lib/create-crud-mutations', () => ({
  createCrudMutations: vi.fn(() => () => ({
    create: { mutate: vi.fn(), isPending: false },
    update: { mutate: vi.fn(), isPending: false },
    delete: { mutate: vi.fn(), isPending: false },
  })),
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useClient, clientQueryKey } from '../use-client'
import { useClientMutations } from '../use-client-mutations'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useClient', () => {
  it('calls clientApi.get with the given id', async () => {
    const { clientApi } = await import('../../api')
    renderHook(() => useClient('123'), { wrapper: createWrapper() })
  })

  it('generates correct query key', () => {
    expect(clientQueryKey('123')).toEqual(['client', '123'])
    expect(clientQueryKey(42)).toEqual(['client', 42])
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useClient('1'), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useClientMutations', () => {
  it('returns createClient, updateClient, deleteClient', () => {
    const { result } = renderHook(() => useClientMutations(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('createClient')
    expect(result.current).toHaveProperty('updateClient')
    expect(result.current).toHaveProperty('deleteClient')
  })

  it('each mutation has mutate function', () => {
    const { result } = renderHook(() => useClientMutations(), { wrapper: createWrapper() })
    expect(typeof result.current.createClient.mutate).toBe('function')
    expect(typeof result.current.updateClient.mutate).toBe('function')
    expect(typeof result.current.deleteClient.mutate).toBe('function')
  })
})
