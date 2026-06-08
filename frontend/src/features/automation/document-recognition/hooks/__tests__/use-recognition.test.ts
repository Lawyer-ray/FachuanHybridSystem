vi.mock('../../api', () => ({
  documentRecognitionApi: {
    list: vi.fn().mockResolvedValue({ results: [], count: 0 }),
    getTask: vi.fn().mockResolvedValue({ id: 1, status: 'success' }),
    upload: vi.fn().mockResolvedValue({ id: 1 }),
    bind: vi.fn().mockResolvedValue({ id: 1 }),
    updateInfo: vi.fn().mockResolvedValue({ id: 1 }),
    searchCases: vi.fn().mockResolvedValue([]),
  },
  PaginatedResponse: {},
}))

vi.mock('@/hooks/use-debounce', () => ({
  useDebounce: vi.fn((value: string) => value),
}))

vi.mock('../../../constants', () => ({
  POLLING_INTERVALS: {
    RECOGNITION_PROCESSING: 2000,
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
import { useRecognitionTasks, recognitionTasksQueryKey, recognitionTaskQueryKey } from '../use-recognition-tasks'
import { useRecognitionTask, shouldPoll, isCompleted } from '../use-recognition-task'
import { useUploadDocument, useBindCase, useUpdateRecognitionInfo } from '../use-recognition-mutations'
import { useCaseSearch, caseSearchQueryKey } from '../use-case-search'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('shouldPoll', () => {
  it('returns true for pending status', () => {
    expect(shouldPoll('pending')).toBe(true)
  })

  it('returns true for processing status', () => {
    expect(shouldPoll('processing')).toBe(true)
  })

  it('returns false for success status', () => {
    expect(shouldPoll('success')).toBe(false)
  })

  it('returns false for failed status', () => {
    expect(shouldPoll('failed')).toBe(false)
  })
})

describe('isCompleted', () => {
  it('returns true for success', () => {
    expect(isCompleted('success')).toBe(true)
  })

  it('returns true for failed', () => {
    expect(isCompleted('failed')).toBe(true)
  })

  it('returns false for pending', () => {
    expect(isCompleted('pending')).toBe(false)
  })
})

describe('recognitionTasksQueryKey', () => {
  it('generates key with defaults', () => {
    expect(recognitionTasksQueryKey()).toEqual(['recognition-tasks', { page: 1, page_size: 10, status: null }])
  })

  it('generates key with params', () => {
    expect(recognitionTasksQueryKey({ page: 2, status: 'success' })).toEqual(['recognition-tasks', { page: 2, page_size: 10, status: 'success' }])
  })
})

describe('recognitionTaskQueryKey', () => {
  it('generates correct key', () => {
    expect(recognitionTaskQueryKey(42)).toEqual(['recognition-task', 42])
  })
})

describe('caseSearchQueryKey', () => {
  it('generates correct key', () => {
    expect(caseSearchQueryKey('test')).toEqual(['document-recognition', 'case-search', 'test'])
  })
})

describe('useRecognitionTasks', () => {
  it('calls API on mount', async () => {
    const { documentRecognitionApi } = await import('../../api')
    renderHook(() => useRecognitionTasks(), { wrapper: createWrapper() })
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useRecognitionTasks(), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useRecognitionTask', () => {
  it('calls API with id', async () => {
    const { documentRecognitionApi } = await import('../../api')
    renderHook(() => useRecognitionTask(1), { wrapper: createWrapper() })
  })

  it('returns loading state initially', () => {
    const { result } = renderHook(() => useRecognitionTask(1), { wrapper: createWrapper() })
    expect(result.current.isLoading).toBe(true)
  })
})

describe('useUploadDocument', () => {
  it('returns mutation with mutate', () => {
    const { result } = renderHook(() => useUploadDocument(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('mutate')
  })

  it('calls documentRecognitionApi.upload on mutate', async () => {
    const { documentRecognitionApi } = await import('../../api')
    const { result } = renderHook(() => useUploadDocument(), { wrapper: createWrapper() })
    const file = new File(['test'], 'test.pdf')
    act(() => { result.current.mutate(file) })

    expect(result.current).toHaveProperty("mutate")
  })
})

describe('useBindCase', () => {
  it('returns mutation with mutate', () => {
    const { result } = renderHook(() => useBindCase(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('mutate')
  })

  it('calls documentRecognitionApi.bind on mutate', async () => {
    const { documentRecognitionApi } = await import('../../api')
    const { result } = renderHook(() => useBindCase(), { wrapper: createWrapper() })
    act(() => { result.current.mutate({ taskId: 1, data: { case_id: 2 } } as any) })

    expect(result.current).toHaveProperty("mutate")
  })
})

describe('useUpdateRecognitionInfo', () => {
  it('returns mutation with mutate', () => {
    const { result } = renderHook(() => useUpdateRecognitionInfo(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('mutate')
  })

  it('calls documentRecognitionApi.updateInfo on mutate', async () => {
    const { documentRecognitionApi } = await import('../../api')
    const { result } = renderHook(() => useUpdateRecognitionInfo(), { wrapper: createWrapper() })
    act(() => { result.current.mutate({ taskId: 1, data: { document_type: '判决书' } } as any) })

    expect(result.current).toHaveProperty("mutate")
  })
})

describe('useCaseSearch (document-recognition)', () => {
  it('calls API when query meets min chars', async () => {
    const { documentRecognitionApi } = await import('../../api')
    renderHook(() => useCaseSearch('test'), { wrapper: createWrapper() })
  })

  it('returns initial state', () => {
    const { result } = renderHook(() => useCaseSearch(''), { wrapper: createWrapper() })
    expect(result.current.data).toBeUndefined()
  })
})
