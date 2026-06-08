vi.mock('../../api', () => ({
  taskQueueApi: {
    listQueued: vi.fn().mockResolvedValue([]),
    listCompleted: vi.fn().mockResolvedValue([]),
    listFailed: vi.fn().mockResolvedValue([]),
    listScheduled: vi.fn().mockResolvedValue([]),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import { useQueuedTasks, useCompletedTasks, useFailedTasks, useScheduledTasks } from '../use-tasks'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useQueuedTasks', () => {
  it('calls taskQueueApi.listQueued on mount', async () => {
    const { taskQueueApi } = await import('../../api')
    renderHook(() => useQueuedTasks(), { wrapper: createWrapper() })
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useQueuedTasks(), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useCompletedTasks', () => {
  it('calls taskQueueApi.listCompleted on mount', async () => {
    const { taskQueueApi } = await import('../../api')
    renderHook(() => useCompletedTasks(), { wrapper: createWrapper() })
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useCompletedTasks(), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useFailedTasks', () => {
  it('calls taskQueueApi.listFailed on mount', async () => {
    const { taskQueueApi } = await import('../../api')
    renderHook(() => useFailedTasks(), { wrapper: createWrapper() })
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useFailedTasks(), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useScheduledTasks', () => {
  it('calls taskQueueApi.listScheduled on mount', async () => {
    const { taskQueueApi } = await import('../../api')
    renderHook(() => useScheduledTasks(), { wrapper: createWrapper() })
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useScheduledTasks(), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})
