vi.mock('../../api', () => ({
  caseApi: {
    getTemplateBindings: vi.fn().mockResolvedValue({ bindings: [] }),
    getAvailableTemplates: vi.fn().mockResolvedValue([]),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useTemplateBindings, useAvailableTemplates } from '../use-template-bindings'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useTemplateBindings', () => {
  it('calls API when caseId is provided', async () => {
    const { caseApi } = await import('../../api')
    renderHook(() => useTemplateBindings(1), { wrapper: createWrapper() })
  })

  it('does not call API when caseId is undefined', async () => {
    const { caseApi } = await import('../../api')
    ;(caseApi.getTemplateBindings as any).mockClear()
    renderHook(() => useTemplateBindings(undefined), { wrapper: createWrapper() })
    expect(caseApi.getTemplateBindings).not.toHaveBeenCalled()
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useTemplateBindings(1), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useAvailableTemplates', () => {
  it('calls API when caseId is provided', async () => {
    const { caseApi } = await import('../../api')
    renderHook(() => useAvailableTemplates(1), { wrapper: createWrapper() })
  })

  it('does not call API when caseId is undefined', async () => {
    const { caseApi } = await import('../../api')
    ;(caseApi.getAvailableTemplates as any).mockClear()
    renderHook(() => useAvailableTemplates(undefined), { wrapper: createWrapper() })
    expect(caseApi.getAvailableTemplates).not.toHaveBeenCalled()
  })
})
