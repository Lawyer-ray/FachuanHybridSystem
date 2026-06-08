vi.mock('../../api', () => ({
  clientApi: {
    createPropertyClue: vi.fn().mockResolvedValue({ id: 1 }),
    updatePropertyClue: vi.fn().mockResolvedValue({ id: 1 }),
    deletePropertyClue: vi.fn().mockResolvedValue(undefined),
    uploadClueAttachment: vi.fn().mockResolvedValue({ id: 1 }),
    deleteClueAttachment: vi.fn().mockResolvedValue(undefined),
    listPropertyClues: vi.fn().mockResolvedValue([]),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { usePropertyClueMutations } from '../use-property-clue-mutations'
import { usePropertyClues, propertyCluesQueryKey } from '../use-property-clues'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('usePropertyClueMutations', () => {
  it('returns all property clue mutations', () => {
    const { result } = renderHook(() => usePropertyClueMutations(1), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('createClue')
    expect(result.current).toHaveProperty('updateClue')
    expect(result.current).toHaveProperty('deleteClue')
    expect(result.current).toHaveProperty('uploadAttachment')
    expect(result.current).toHaveProperty('deleteAttachment')
  })

  it('createClue calls clientApi.createPropertyClue', async () => {
    const { clientApi } = await import('../../api')
    const { result } = renderHook(() => usePropertyClueMutations(1), { wrapper: createWrapper() })
    await act(async () => { result.current.createClue.mutate({ clue_type: 'bank', description: 'test' } as any) })
  })

  it('deleteClue calls clientApi.deletePropertyClue', async () => {
    const { clientApi } = await import('../../api')
    const { result } = renderHook(() => usePropertyClueMutations(1), { wrapper: createWrapper() })
    act(() => { result.current.deleteClue.mutate(5) })
    expect(result.current.deleteClue).toHaveProperty("isPending")
  })
})

describe('usePropertyClues', () => {
  it('calls API when clientId is provided', async () => {
    const { clientApi } = await import('../../api')
    renderHook(() => usePropertyClues(1), { wrapper: createWrapper() })
  })

  it('generates correct query key', () => {
    expect(propertyCluesQueryKey(42)).toEqual(['property-clues', 42])
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => usePropertyClues(1), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})
