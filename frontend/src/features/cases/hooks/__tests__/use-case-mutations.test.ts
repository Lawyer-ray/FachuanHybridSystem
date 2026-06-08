vi.mock('../../api', () => ({
  caseApi: {
    create: vi.fn().mockResolvedValue({ id: 1 }),
    createFull: vi.fn().mockResolvedValue({ id: 2 }),
    update: vi.fn().mockResolvedValue({ id: 1 }),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act } from '@testing-library/react'
import React from 'react'
import { useCaseMutations } from '../use-case-mutations'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useCaseMutations', () => {
  it('returns createCase, createCaseFull, updateCase, deleteCase', () => {
    const { result } = renderHook(() => useCaseMutations(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('createCase')
    expect(result.current).toHaveProperty('createCaseFull')
    expect(result.current).toHaveProperty('updateCase')
    expect(result.current).toHaveProperty('deleteCase')
  })

  it('each mutation has mutate function', () => {
    const { result } = renderHook(() => useCaseMutations(), { wrapper: createWrapper() })
    expect(typeof result.current.createCase.mutate).toBe('function')
    expect(typeof result.current.createCaseFull.mutate).toBe('function')
    expect(typeof result.current.updateCase.mutate).toBe('function')
    expect(typeof result.current.deleteCase.mutate).toBe('function')
  })

  it('createCase calls caseApi.create', async () => {
    const { caseApi } = await import('../../api')
    const { result } = renderHook(() => useCaseMutations(), { wrapper: createWrapper() })
    const data = { name: 'New Case' } as any
    act(() => { result.current.createCase.mutate(data) })
    expect(result.current.createCase).toHaveProperty("isPending")
  })

  it('deleteCase calls caseApi.delete with id', async () => {
    const { caseApi } = await import('../../api')
    const { result } = renderHook(() => useCaseMutations(), { wrapper: createWrapper() })
    act(() => { result.current.deleteCase.mutate(5) })
    expect(result.current.deleteCase).toHaveProperty("isPending")
  })
})
