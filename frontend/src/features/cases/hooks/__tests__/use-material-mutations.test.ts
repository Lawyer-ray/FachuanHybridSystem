vi.mock('../../api', () => ({
  caseApi: {
    uploadMaterials: vi.fn().mockResolvedValue({}),
    bindMaterials: vi.fn().mockResolvedValue({}),
    replaceMaterial: vi.fn().mockResolvedValue({}),
    renameMaterialGroup: vi.fn().mockResolvedValue({}),
    deleteMaterial: vi.fn().mockResolvedValue(undefined),
    deleteAllMaterials: vi.fn().mockResolvedValue(undefined),
    saveMaterialGroupOrder: vi.fn().mockResolvedValue({}),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useMaterialMutations } from '../use-material-mutations'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useMaterialMutations', () => {
  it('returns all material mutations', () => {
    const { result } = renderHook(() => useMaterialMutations(1), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('uploadMaterials')
    expect(result.current).toHaveProperty('bindMaterials')
    expect(result.current).toHaveProperty('replaceMaterial')
    expect(result.current).toHaveProperty('renameGroup')
    expect(result.current).toHaveProperty('deleteMaterial')
    expect(result.current).toHaveProperty('deleteAllMaterials')
    expect(result.current).toHaveProperty('saveGroupOrder')
  })

  it('deleteMaterial calls caseApi.deleteMaterial', async () => {
    const { caseApi } = await import('../../api')
    const { result } = renderHook(() => useMaterialMutations(1), { wrapper: createWrapper() })
    act(() => { result.current.deleteMaterial.mutate(5) })
    expect(result.current.deleteMaterial).toHaveProperty("isPending")
  })

  it('replaceMaterial calls caseApi.replaceMaterial', async () => {
    const { caseApi } = await import('../../api')
    const { result } = renderHook(() => useMaterialMutations(1), { wrapper: createWrapper() })
    await act(async () => { result.current.replaceMaterial.mutate({ materialId: 3, newAttachmentId: 7 }) })
  })
})
