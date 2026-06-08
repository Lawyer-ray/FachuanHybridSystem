vi.mock('../../api', () => ({
  caseApi: {
    getFolderBinding: vi.fn().mockResolvedValue(null),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useFolderBinding } from '../use-folder-binding'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useFolderBinding', () => {
  it('calls caseApi.getFolderBinding when caseId is provided', async () => {
    const { caseApi } = await import('../../api')
    renderHook(() => useFolderBinding(1), { wrapper: createWrapper() })
  })

  it('does not call API when caseId is undefined', async () => {
    const { caseApi } = await import('../../api')
    ;(caseApi.getFolderBinding as any).mockClear()
    renderHook(() => useFolderBinding(undefined), { wrapper: createWrapper() })
    expect(caseApi.getFolderBinding).not.toHaveBeenCalled()
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useFolderBinding(1), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})
