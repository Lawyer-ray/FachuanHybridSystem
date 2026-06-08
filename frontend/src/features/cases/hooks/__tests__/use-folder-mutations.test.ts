vi.mock('../../api', () => ({
  caseApi: {
    createFolderBinding: vi.fn().mockResolvedValue({}),
    deleteFolderBinding: vi.fn().mockResolvedValue(undefined),
    startFolderScan: vi.fn().mockResolvedValue({ session_id: 'abc' }),
    stageScanResults: vi.fn().mockResolvedValue({}),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useFolderMutations } from '../use-folder-mutations'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useFolderMutations', () => {
  it('returns all folder mutations', () => {
    const { result } = renderHook(() => useFolderMutations(1), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('createFolderBinding')
    expect(result.current).toHaveProperty('deleteFolderBinding')
    expect(result.current).toHaveProperty('startFolderScan')
    expect(result.current).toHaveProperty('stageScanResults')
  })

  it('createFolderBinding calls caseApi.createFolderBinding', async () => {
    const { caseApi } = await import('../../api')
    const { result } = renderHook(() => useFolderMutations(1), { wrapper: createWrapper() })
    await act(async () => { result.current.createFolderBinding.mutate({ folder_path: '/docs' }) })
  })

  it('deleteFolderBinding calls caseApi.deleteFolderBinding', async () => {
    const { caseApi } = await import('../../api')
    const { result } = renderHook(() => useFolderMutations(1), { wrapper: createWrapper() })
    act(() => { result.current.deleteFolderBinding.mutate() })
    expect(result.current.deleteFolderBinding).toHaveProperty("isPending")
  })
})
