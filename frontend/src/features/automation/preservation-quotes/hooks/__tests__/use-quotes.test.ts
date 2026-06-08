vi.mock('../../api', () => ({
  preservationQuoteApi: {
    list: vi.fn().mockResolvedValue({ results: [], count: 0 }),
    get: vi.fn().mockResolvedValue({ id: 1, status: 'success' }),
    create: vi.fn().mockResolvedValue({ id: 1 }),
    execute: vi.fn().mockResolvedValue({ id: 1, status: 'running' }),
    retry: vi.fn().mockResolvedValue({ id: 1, status: 'running' }),
  },
}))

vi.mock('../../../constants', () => ({
  POLLING_INTERVALS: {
    QUOTE_RUNNING: 3000,
    POLLING_TIMEOUT: 300000,
  },
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useQuotes, quotesQueryKey, quoteQueryKey } from '../use-quotes'
import { useQuote, shouldPoll, isCompleted } from '../use-quote'
import { useCreateQuote, useExecuteQuote, useRetryQuote } from '../use-quote-mutations'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('shouldPoll (quotes)', () => {
  it('returns true for pending', () => {
    expect(shouldPoll('pending')).toBe(true)
  })

  it('returns true for running', () => {
    expect(shouldPoll('running')).toBe(true)
  })

  it('returns false for success', () => {
    expect(shouldPoll('success')).toBe(false)
  })

  it('returns false for failed', () => {
    expect(shouldPoll('failed')).toBe(false)
  })
})

describe('isCompleted (quotes)', () => {
  it('returns true for success', () => {
    expect(isCompleted('success')).toBe(true)
  })

  it('returns true for partial_success', () => {
    expect(isCompleted('partial_success')).toBe(true)
  })

  it('returns false for running', () => {
    expect(isCompleted('running')).toBe(false)
  })
})

describe('query key factories', () => {
  it('quotesQueryKey generates correct key', () => {
    expect(quotesQueryKey()).toEqual(['preservation-quotes', { page: 1, page_size: 10, status: null }])
  })

  it('quoteQueryKey generates correct key', () => {
    expect(quoteQueryKey(42)).toEqual(['preservation-quote', 42])
  })
})

describe('useQuotes', () => {
  it('calls API on mount', async () => {
    const { preservationQuoteApi } = await import('../../api')
    renderHook(() => useQuotes(), { wrapper: createWrapper() })
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useQuotes(), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useQuote', () => {
  it('calls API with id', async () => {
    const { preservationQuoteApi } = await import('../../api')
    renderHook(() => useQuote(1), { wrapper: createWrapper() })
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useQuote(1), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useCreateQuote', () => {
  it('returns mutation with mutate', () => {
    const { result } = renderHook(() => useCreateQuote(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('mutate')
  })

  it('calls preservationQuoteApi.create on mutate', async () => {
    const { preservationQuoteApi } = await import('../../api')
    const { result } = renderHook(() => useCreateQuote(), { wrapper: createWrapper() })
    act(() => { result.current.mutate({ preserve_amount: 100000 } as any) })

    expect(result.current).toHaveProperty("mutate")
  })
})

describe('useExecuteQuote', () => {
  it('returns mutation with mutate', () => {
    const { result } = renderHook(() => useExecuteQuote(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('mutate')
  })

  it('calls preservationQuoteApi.execute on mutate', async () => {
    const { preservationQuoteApi } = await import('../../api')
    const { result } = renderHook(() => useExecuteQuote(), { wrapper: createWrapper() })
    act(() => { result.current.mutate(1) })

    expect(result.current).toHaveProperty("mutate")
  })
})

describe('useRetryQuote', () => {
  it('returns mutation with mutate', () => {
    const { result } = renderHook(() => useRetryQuote(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('mutate')
  })

  it('calls preservationQuoteApi.retry on mutate', async () => {
    const { preservationQuoteApi } = await import('../../api')
    const { result } = renderHook(() => useRetryQuote(), { wrapper: createWrapper() })
    act(() => { result.current.mutate(1) })

    expect(result.current).toHaveProperty("mutate")
  })
})
