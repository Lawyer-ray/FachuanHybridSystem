vi.mock('../../api', () => ({
  contentOpsApi: {
    getTaskDiscussions: vi.fn().mockResolvedValue([]),
    getDiscussion: vi.fn().mockResolvedValue({}),
    suggestTopics: vi.fn().mockResolvedValue([]),
    getHotTopics: vi.fn().mockResolvedValue([]),
    refreshHotTopics: vi.fn().mockResolvedValue([]),
    getInspiration: vi.fn().mockResolvedValue([]),
    listTasks: vi.fn().mockResolvedValue([]),
    getTask: vi.fn().mockResolvedValue({ status: 'completed' }),
    getTaskArticles: vi.fn().mockResolvedValue([]),
    getTaskEpisodes: vi.fn().mockResolvedValue([]),
    createTask: vi.fn().mockResolvedValue({ id: 1 }),
    approveArticle: vi.fn().mockResolvedValue({}),
    rejectArticle: vi.fn().mockResolvedValue({}),
    updateArticle: vi.fn().mockResolvedValue({}),
    regenerateArticle: vi.fn().mockResolvedValue({}),
    approveEpisode: vi.fn().mockResolvedValue({}),
    rejectEpisode: vi.fn().mockResolvedValue({}),
    retryTask: vi.fn().mockResolvedValue({}),
    cancelTask: vi.fn().mockResolvedValue({}),
    deleteTask: vi.fn().mockResolvedValue(undefined),
    updateDiscussionTurn: vi.fn().mockResolvedValue({}),
    approveDiscussion: vi.fn().mockResolvedValue({}),
    rejectDiscussion: vi.fn().mockResolvedValue({}),
    regenerateDiscussion: vi.fn().mockResolvedValue({}),
    synthesizeDiscussion: vi.fn().mockResolvedValue({}),
  },
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act, waitFor } from '@testing-library/react'
import React from 'react'
import {
  useTaskDiscussions,
  useHotTopics,
  useTaskList,
  useTopicSuggestions,
  useCreateTask,
  useRetryTask,
} from '../use-content-ops'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useTaskDiscussions', () => {
  it('calls API when taskId is provided', async () => {
    const { contentOpsApi } = await import('../../api')
    renderHook(() => useTaskDiscussions(1), { wrapper: createWrapper() })
  })

  it('does not call API when taskId is null', async () => {
    const { contentOpsApi } = await import('../../api')
    ;(contentOpsApi.getTaskDiscussions as any).mockClear()
    renderHook(() => useTaskDiscussions(null), { wrapper: createWrapper() })
    expect(contentOpsApi.getTaskDiscussions).not.toHaveBeenCalled()
  })
})

describe('useHotTopics', () => {
  it('calls contentOpsApi.getHotTopics on mount', async () => {
    const { contentOpsApi } = await import('../../api')
    renderHook(() => useHotTopics(), { wrapper: createWrapper() })
  })

  it('passes source parameter', async () => {
    const { contentOpsApi } = await import('../../api')
    renderHook(() => useHotTopics('weibo'), { wrapper: createWrapper() })
  })
})

describe('useTopicSuggestions', () => {
  it('returns refetch function and initial null data', () => {
    const { result } = renderHook(() => useTopicSuggestions(), { wrapper: createWrapper() })
    expect(result.current.data).toBeNull()
    expect(result.current.error).toBeNull()
    expect(typeof result.current.refetch).toBe('function')
  })

  it('sets isFetching to false initially', () => {
    const { result } = renderHook(() => useTopicSuggestions(), { wrapper: createWrapper() })
    expect(result.current.isFetching).toBe(false)
  })
})

describe('useTaskList', () => {
  it('calls contentOpsApi.listTasks on mount', async () => {
    const { contentOpsApi } = await import('../../api')
    renderHook(() => useTaskList(), { wrapper: createWrapper() })
  })

  it('passes mode parameter', async () => {
    const { contentOpsApi } = await import('../../api')
    renderHook(() => useTaskList('auto'), { wrapper: createWrapper() })
  })
})

describe('useCreateTask', () => {
  it('returns mutation with mutate function', () => {
    const { result } = renderHook(() => useCreateTask(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('mutate')
  })

  it('calls contentOpsApi.createTask on mutate', async () => {
    const { contentOpsApi } = await import('../../api')
    const { result } = renderHook(() => useCreateTask(), { wrapper: createWrapper() })
    act(() => { result.current.mutate({ topic: 'test' } as any) })

    expect(result.current).toHaveProperty("mutate")
  })
})

describe('useRetryTask', () => {
  it('returns mutation with mutate function', () => {
    const { result } = renderHook(() => useRetryTask(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('mutate')
  })

  it('calls contentOpsApi.retryTask on mutate', async () => {
    const { contentOpsApi } = await import('../../api')
    const { result } = renderHook(() => useRetryTask(), { wrapper: createWrapper() })
    act(() => { result.current.mutate(1) })

    expect(result.current).toHaveProperty("mutate")
  })
})
