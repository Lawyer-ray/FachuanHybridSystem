vi.mock('@/lib/api', () => ({
  createFeatureApiClient: vi.fn(() => ({
    get: vi.fn(() => ({
      json: vi.fn().mockResolvedValue([
        { id: 1, name: 'Client A', client_type: 'individual', client_type_label: '个人', is_our_client: true },
      ]),
    })),
  })),
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import React from 'react'
import { useClientsSelect } from '../use-clients-select'
import { useLawyers } from '../use-lawyers'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useClientsSelect', () => {
  it('returns loading state initially', () => {
    const { result } = renderHook(() => useClientsSelect(), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })

  it('eventually returns data', async () => {
    const { result } = renderHook(() => useClientsSelect(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.data).toBeDefined())
  })

  it('data contains client options', async () => {
    const { result } = renderHook(() => useClientsSelect(), { wrapper: createWrapper() })
    await waitFor(() => {
      expect(result.current.data).toHaveLength(1)
      expect(result.current.data![0]).toHaveProperty('name', 'Client A')
    })
  })
})

describe('useLawyers (contracts)', () => {
  it('returns loading state initially', () => {
    const { result } = renderHook(() => useLawyers(), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })

  it('eventually returns data', async () => {
    const { result } = renderHook(() => useLawyers(), { wrapper: createWrapper() })
    await waitFor(() => expect(result.current.data).toBeDefined())
  })

  it('returns array data', async () => {
    const { result } = renderHook(() => useLawyers(), { wrapper: createWrapper() })
    await waitFor(() => expect(Array.isArray(result.current.data)).toBe(true))
  })
})
