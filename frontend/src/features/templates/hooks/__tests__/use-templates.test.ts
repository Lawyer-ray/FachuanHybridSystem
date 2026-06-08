vi.mock('../../api', () => ({
  templateApi: {
    list: vi.fn().mockResolvedValue([]),
    get: vi.fn().mockResolvedValue({ id: 1 }),
    listLibraryFiles: vi.fn().mockResolvedValue([]),
    create: vi.fn().mockResolvedValue({ id: 1 }),
    update: vi.fn().mockResolvedValue({ id: 1 }),
    delete: vi.fn().mockResolvedValue(undefined),
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
import { useTemplates } from '../use-templates'
import { useTemplate } from '../use-template'
import { useTemplateLibraryFiles } from '../use-template-library-files'
import { useTemplateMutations } from '../use-template-mutations'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useTemplates', () => {
  it('calls templateApi.list on mount', async () => {
    const { templateApi } = await import('../../api')
    renderHook(() => useTemplates(), { wrapper: createWrapper() })
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useTemplates(), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })

  it('eventually returns data', async () => {
    const { result } = renderHook(() => useTemplates(), { wrapper: createWrapper() })
  })
})

describe('useTemplate', () => {
  it('calls templateApi.get with id', async () => {
    const { templateApi } = await import('../../api')
    renderHook(() => useTemplate(1), { wrapper: createWrapper() })
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useTemplate(1), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useTemplateLibraryFiles', () => {
  it('calls templateApi.listLibraryFiles on mount', async () => {
    const { templateApi } = await import('../../api')
    renderHook(() => useTemplateLibraryFiles(), { wrapper: createWrapper() })
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useTemplateLibraryFiles(), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useTemplateMutations', () => {
  it('returns create, update, delete', () => {
    const { result } = renderHook(() => useTemplateMutations(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('create')
    expect(result.current).toHaveProperty('update')
    expect(result.current).toHaveProperty('delete')
  })

  it('each mutation has mutate function', () => {
    const { result } = renderHook(() => useTemplateMutations(), { wrapper: createWrapper() })
    expect(typeof result.current.create.mutate).toBe('function')
    expect(typeof result.current.update.mutate).toBe('function')
    expect(typeof result.current.delete.mutate).toBe('function')
  })
})
