vi.mock('../../api', () => ({
  caseApi: {
    bindTemplate: vi.fn().mockResolvedValue({}),
    unbindTemplate: vi.fn().mockResolvedValue(undefined),
    generateTemplate: vi.fn().mockResolvedValue({}),
    unifiedGenerate: vi.fn().mockResolvedValue({}),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act } from '@testing-library/react'
import React from 'react'
import { useTemplateMutations } from '../use-template-mutations'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useTemplateMutations', () => {
  it('returns all template mutations', () => {
    const { result } = renderHook(() => useTemplateMutations(1), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('bindTemplate')
    expect(result.current).toHaveProperty('unbindTemplate')
    expect(result.current).toHaveProperty('generateTemplate')
    expect(result.current).toHaveProperty('unifiedGenerate')
  })

  it('bindTemplate calls caseApi.bindTemplate', async () => {
    const { caseApi } = await import('../../api')
    const { result } = renderHook(() => useTemplateMutations(1), { wrapper: createWrapper() })
    act(() => { result.current.bindTemplate.mutate(10) })
    expect(result.current.bindTemplate).toHaveProperty("isPending")
  })

  it('unbindTemplate calls caseApi.unbindTemplate', async () => {
    const { caseApi } = await import('../../api')
    const { result } = renderHook(() => useTemplateMutations(1), { wrapper: createWrapper() })
    act(() => { result.current.unbindTemplate.mutate(5) })
    expect(result.current.unbindTemplate).toHaveProperty("isPending")
  })
})
