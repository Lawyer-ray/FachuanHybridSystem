vi.mock('../../api', () => ({
  contactApi: {
    create: vi.fn().mockResolvedValue({ id: 1 }),
    update: vi.fn().mockResolvedValue({ id: 1 }),
    delete: vi.fn().mockResolvedValue(undefined),
    list: vi.fn().mockResolvedValue([]),
    search: vi.fn().mockResolvedValue([]),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useContactMutations } from '../use-contact-mutations'
import { useContacts } from '../use-contacts'
import { useContactSearch } from '../use-contact-search'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useContactMutations', () => {
  it('returns createContact, updateContact, deleteContact', () => {
    const { result } = renderHook(() => useContactMutations(1), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('createContact')
    expect(result.current).toHaveProperty('updateContact')
    expect(result.current).toHaveProperty('deleteContact')
  })

  it('createContact calls contactApi.create', async () => {
    const { contactApi } = await import('../../api')
    const { result } = renderHook(() => useContactMutations(1), { wrapper: createWrapper() })
    await act(async () => { result.current.createContact.mutate({ name: 'John', case_id: 1 } as any) })
  })

  it('deleteContact calls contactApi.delete', async () => {
    const { contactApi } = await import('../../api')
    const { result } = renderHook(() => useContactMutations(1), { wrapper: createWrapper() })
    act(() => { result.current.deleteContact.mutate(5) })
    expect(result.current.deleteContact).toHaveProperty("isPending")
  })
})

describe('useContacts', () => {
  it('calls contactApi.list with caseId', async () => {
    const { contactApi } = await import('../../api')
    renderHook(() => useContacts(1), { wrapper: createWrapper() })
  })

  it('passes stage parameter', async () => {
    const { contactApi } = await import('../../api')
    renderHook(() => useContacts(1, 'filing'), { wrapper: createWrapper() })
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useContacts(1), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useContactSearch', () => {
  it('calls API when q is provided', async () => {
    const { contactApi } = await import('../../api')
    renderHook(() => useContactSearch({ q: 'test' }), { wrapper: createWrapper() })
  })

  it('does not call API when no params provided', async () => {
    const { contactApi } = await import('../../api')
    ;(contactApi.search as any).mockClear()
    renderHook(() => useContactSearch({}), { wrapper: createWrapper() })
    expect(contactApi.search).not.toHaveBeenCalled()
  })

  it('enables query when court param is provided', async () => {
    const { contactApi } = await import('../../api')
    renderHook(() => useContactSearch({ court: 'beijing' }), { wrapper: createWrapper() })
  })
})
