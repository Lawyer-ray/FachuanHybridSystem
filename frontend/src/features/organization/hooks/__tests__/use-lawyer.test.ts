vi.mock('../../api', () => ({
  lawyerApi: {
    create: vi.fn().mockResolvedValue({ id: 1 }),
    update: vi.fn().mockResolvedValue({ id: 1 }),
    delete: vi.fn().mockResolvedValue(undefined),
    get: vi.fn().mockResolvedValue({ id: '1', real_name: 'Test Lawyer' }),
    list: vi.fn().mockResolvedValue([]),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useLawyerMutations } from '../use-lawyer-mutations'
import { useLawyer, lawyerQueryKey } from '../use-lawyer'
import { useLawyers, lawyersQueryKey } from '../use-lawyers'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useLawyerMutations', () => {
  it('returns createLawyer, updateLawyer, deleteLawyer', () => {
    const { result } = renderHook(() => useLawyerMutations(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('createLawyer')
    expect(result.current).toHaveProperty('updateLawyer')
    expect(result.current).toHaveProperty('deleteLawyer')
  })

  it('createLawyer calls lawyerApi.create', async () => {
    const { lawyerApi } = await import('../../api')
    const { result } = renderHook(() => useLawyerMutations(), { wrapper: createWrapper() })
    await act(async () => { result.current.createLawyer.mutate({ data: { username: 'test', real_name: 'Test' } as any }) })
  })

  it('deleteLawyer calls lawyerApi.delete', async () => {
    const { lawyerApi } = await import('../../api')
    const { result } = renderHook(() => useLawyerMutations(), { wrapper: createWrapper() })
    act(() => { result.current.deleteLawyer.mutate(5) })
    expect(result.current.deleteLawyer).toHaveProperty("isPending")
  })
})

describe('useLawyer', () => {
  it('calls lawyerApi.get with id', async () => {
    const { lawyerApi } = await import('../../api')
    renderHook(() => useLawyer('123'), { wrapper: createWrapper() })
  })

  it('generates correct query key', () => {
    expect(lawyerQueryKey('123')).toEqual(['lawyer', '123'])
    expect(lawyerQueryKey(42)).toEqual(['lawyer', 42])
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useLawyer('1'), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useLawyers', () => {
  it('calls lawyerApi.list on mount', async () => {
    const { lawyerApi } = await import('../../api')
    renderHook(() => useLawyers(), { wrapper: createWrapper() })
  })

  it('passes search parameter to list', async () => {
    const { lawyerApi } = await import('../../api')
    renderHook(() => useLawyers({ search: 'zhang' }), { wrapper: createWrapper() })
  })

  it('generates correct query key with search', () => {
    expect(lawyersQueryKey()).toEqual(['lawyers', { search: '' }])
    expect(lawyersQueryKey({ search: 'test' })).toEqual(['lawyers', { search: 'test' }])
  })
})
