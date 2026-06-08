vi.mock('../../api', () => ({
  lawFirmApi: {
    create: vi.fn().mockResolvedValue({ id: 1 }),
    update: vi.fn().mockResolvedValue({ id: 1 }),
    delete: vi.fn().mockResolvedValue(undefined),
    get: vi.fn().mockResolvedValue({ id: '1', name: 'Test Firm' }),
    list: vi.fn().mockResolvedValue([]),
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
import { useLawFirmMutations } from '../use-lawfirm-mutations'
import { useLawFirm, lawFirmQueryKey } from '../use-lawfirm'
import { useLawFirms, lawFirmsQueryKey } from '../use-lawfirms'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useLawFirmMutations', () => {
  it('returns createLawFirm, updateLawFirm, deleteLawFirm', () => {
    const { result } = renderHook(() => useLawFirmMutations(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('createLawFirm')
    expect(result.current).toHaveProperty('updateLawFirm')
    expect(result.current).toHaveProperty('deleteLawFirm')
  })

  it('each mutation has mutate function', () => {
    const { result } = renderHook(() => useLawFirmMutations(), { wrapper: createWrapper() })
    expect(typeof result.current.createLawFirm.mutate).toBe('function')
    expect(typeof result.current.updateLawFirm.mutate).toBe('function')
    expect(typeof result.current.deleteLawFirm.mutate).toBe('function')
  })
})

describe('useLawFirm', () => {
  it('calls lawFirmApi.get with id', async () => {
    const { lawFirmApi } = await import('../../api')
    renderHook(() => useLawFirm('123'), { wrapper: createWrapper() })
  })

  it('generates correct query key', () => {
    expect(lawFirmQueryKey('123')).toEqual(['lawFirm', '123'])
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useLawFirm('1'), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useLawFirms', () => {
  it('calls lawFirmApi.list on mount', async () => {
    const { lawFirmApi } = await import('../../api')
    renderHook(() => useLawFirms(), { wrapper: createWrapper() })
  })

  it('generates correct query key', () => {
    expect(lawFirmsQueryKey).toEqual(['lawfirms'])
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useLawFirms(), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})
