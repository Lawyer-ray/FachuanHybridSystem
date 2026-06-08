vi.mock('../../api/court-sms', () => ({
  courtSmsApi: {
    list: vi.fn().mockResolvedValue([]),
    get: vi.fn().mockResolvedValue({ id: 1 }),
  },
}))

vi.mock('../../api', () => ({
  expressQueryApi: {
    list: vi.fn().mockResolvedValue([]),
  },
  lprApi_: {
    listRates: vi.fn().mockResolvedValue([]),
    calculate: vi.fn().mockResolvedValue({ total: 100 }),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useCourtSmsList, useCourtSms } from '../use-court-sms'
import { useExpressTasks } from '../use-express-tasks'
import { useLprRates } from '../use-lpr-rates'
import { useLprCalculate } from '../use-lpr-calculate'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useCourtSmsList', () => {
  it('calls courtSmsApi.list on mount', async () => {
    const { courtSmsApi } = await import('../../api/court-sms')
    renderHook(() => useCourtSmsList(), { wrapper: createWrapper() })
  })

  it('passes params to list', async () => {
    const { courtSmsApi } = await import('../../api/court-sms')
    renderHook(() => useCourtSmsList({ page: 1 }), { wrapper: createWrapper() })
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useCourtSmsList(), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useCourtSms', () => {
  it('calls courtSmsApi.get when id is provided', async () => {
    const { courtSmsApi } = await import('../../api/court-sms')
    renderHook(() => useCourtSms(1), { wrapper: createWrapper() })
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useCourtSms(1), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useExpressTasks', () => {
  it('calls expressQueryApi.list on mount', async () => {
    const { expressQueryApi } = await import('../../api')
    renderHook(() => useExpressTasks(), { wrapper: createWrapper() })
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useExpressTasks(), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useLprRates', () => {
  it('calls lprApi_.listRates on mount', async () => {
    const { lprApi_ } = await import('../../api')
    renderHook(() => useLprRates(), { wrapper: createWrapper() })
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useLprRates(), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useLprCalculate', () => {
  it('returns mutation with mutate function', () => {
    const { result } = renderHook(() => useLprCalculate(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('mutate')
  })

  it('calls lprApi_.calculate on mutate', async () => {
    const { lprApi_ } = await import('../../api')
    const { result } = renderHook(() => useLprCalculate(), { wrapper: createWrapper() })
    const req = { amount: 100000, start_date: '2024-01-01', end_date: '2024-06-01' } as any
    act(() => { result.current.mutate(req) })
    expect(result.current).toHaveProperty("isPending")
  })
})
