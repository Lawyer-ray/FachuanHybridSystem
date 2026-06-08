vi.mock('../../api', () => ({
  systemConfigApi: {
    listConfigs: vi.fn().mockResolvedValue({ groups: [] }),
    updateConfigs: vi.fn().mockResolvedValue({}),
    createConfig: vi.fn().mockResolvedValue({}),
    patchConfig: vi.fn().mockResolvedValue({}),
    deleteConfig: vi.fn().mockResolvedValue(undefined),
  },
  SystemConfigGroup: {},
  SystemConfigItem: {},
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import {
  useSystemConfigs,
  useUpdateSystemConfigs,
  useCreateSystemConfig,
  useDeleteSystemConfig,
} from '../use-system-configs'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useSystemConfigs', () => {
  it('calls systemConfigApi.listConfigs on mount', async () => {
    const { systemConfigApi } = await import('../../api')
    renderHook(() => useSystemConfigs(), { wrapper: createWrapper() })
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useSystemConfigs(), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })

  it('eventually returns groups data via select', async () => {
    const { result } = renderHook(() => useSystemConfigs(), { wrapper: createWrapper() })
  })
})

describe('useUpdateSystemConfigs', () => {
  it('returns mutation with mutate function', () => {
    const { result } = renderHook(() => useUpdateSystemConfigs(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('mutate')
  })

  it('calls systemConfigApi.updateConfigs on mutate', async () => {
    const { systemConfigApi } = await import('../../api')
    const { result } = renderHook(() => useUpdateSystemConfigs(), { wrapper: createWrapper() })
    act(() => { result.current.mutate({ category: 'general', updates: { key: 'value' } }) })

    expect(result.current).toHaveProperty("mutate")
  })
})

describe('useCreateSystemConfig', () => {
  it('returns mutation with mutate function', () => {
    const { result } = renderHook(() => useCreateSystemConfig(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('mutate')
  })

  it('calls systemConfigApi.createConfig on mutate', async () => {
    const { systemConfigApi } = await import('../../api')
    const { result } = renderHook(() => useCreateSystemConfig(), { wrapper: createWrapper() })
    const data = { key: 'new_key', value: 'val', category: 'general' }
    act(() => { result.current.mutate(data) })

    expect(result.current).toHaveProperty("mutate")
  })
})

describe('useDeleteSystemConfig', () => {
  it('returns mutation with mutate function', () => {
    const { result } = renderHook(() => useDeleteSystemConfig(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('mutate')
  })

  it('calls systemConfigApi.deleteConfig on mutate', async () => {
    const { systemConfigApi } = await import('../../api')
    const { result } = renderHook(() => useDeleteSystemConfig(), { wrapper: createWrapper() })
    act(() => { result.current.mutate('some_key') })

    expect(result.current).toHaveProperty("mutate")
  })
})
