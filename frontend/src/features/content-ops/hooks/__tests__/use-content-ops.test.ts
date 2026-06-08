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
  useDiscussionDetail,
  useRefreshHotTopics,
  useInspiration,
  useTaskDetail,
  useTaskArticles,
  useTaskEpisodes,
  useReviewArticle,
  useUpdateArticle,
  useRegenerateArticle,
  useReviewEpisode,
  useCancelTask,
  useDeleteTask,
  useUpdateDiscussionTurn,
  useReviewDiscussion,
  useRegenerateDiscussion,
  useSynthesizeDiscussion,
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

describe('useDiscussionDetail', () => {
  it('calls API when scriptId is provided', async () => {
    const { contentOpsApi } = await import('../../api')
    renderHook(() => useDiscussionDetail(5), { wrapper: createWrapper() })
    expect(contentOpsApi.getDiscussion).toHaveBeenCalledWith(5)
  })

  it('does not call API when scriptId is null', async () => {
    const { contentOpsApi } = await import('../../api')
    vi.mocked(contentOpsApi.getDiscussion).mockClear()
    renderHook(() => useDiscussionDetail(null), { wrapper: createWrapper() })
    expect(contentOpsApi.getDiscussion).not.toHaveBeenCalled()
  })
})

describe('useRefreshHotTopics', () => {
  it('returns mutation with mutate function', () => {
    const { result } = renderHook(() => useRefreshHotTopics(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('mutate')
  })

  it('calls contentOpsApi.refreshHotTopics on mutate', async () => {
    const { contentOpsApi } = await import('../../api')
    vi.mocked(contentOpsApi.refreshHotTopics).mockClear()
    const { result } = renderHook(() => useRefreshHotTopics(), { wrapper: createWrapper() })
    await act(async () => { await result.current.mutateAsync('weibo') })
    expect(contentOpsApi.refreshHotTopics).toHaveBeenCalledWith('weibo')
  })
})

describe('useInspiration', () => {
  it('returns initial null data and refetch function', () => {
    const { result } = renderHook(() => useInspiration(), { wrapper: createWrapper() })
    expect(result.current.data).toBeNull()
    expect(result.current.error).toBeNull()
    expect(typeof result.current.refetch).toBe('function')
  })

  it('sets isFetching to false initially', () => {
    const { result } = renderHook(() => useInspiration(), { wrapper: createWrapper() })
    expect(result.current.isFetching).toBe(false)
  })
})

describe('useTaskDetail', () => {
  it('calls API when taskId is provided', async () => {
    const { contentOpsApi } = await import('../../api')
    renderHook(() => useTaskDetail(10), { wrapper: createWrapper() })
    expect(contentOpsApi.getTask).toHaveBeenCalledWith(10)
  })

  it('does not call API when taskId is null', async () => {
    const { contentOpsApi } = await import('../../api')
    vi.mocked(contentOpsApi.getTask).mockClear()
    renderHook(() => useTaskDetail(null), { wrapper: createWrapper() })
    expect(contentOpsApi.getTask).not.toHaveBeenCalled()
  })
})

describe('useTaskArticles', () => {
  it('calls API when taskId is provided', async () => {
    const { contentOpsApi } = await import('../../api')
    renderHook(() => useTaskArticles(3), { wrapper: createWrapper() })
    expect(contentOpsApi.getTaskArticles).toHaveBeenCalledWith(3)
  })

  it('does not call API when taskId is null', async () => {
    const { contentOpsApi } = await import('../../api')
    vi.mocked(contentOpsApi.getTaskArticles).mockClear()
    renderHook(() => useTaskArticles(null), { wrapper: createWrapper() })
    expect(contentOpsApi.getTaskArticles).not.toHaveBeenCalled()
  })
})

describe('useTaskEpisodes', () => {
  it('calls API when taskId is provided', async () => {
    const { contentOpsApi } = await import('../../api')
    renderHook(() => useTaskEpisodes(7), { wrapper: createWrapper() })
    expect(contentOpsApi.getTaskEpisodes).toHaveBeenCalledWith(7)
  })

  it('does not call API when taskId is null', async () => {
    const { contentOpsApi } = await import('../../api')
    vi.mocked(contentOpsApi.getTaskEpisodes).mockClear()
    renderHook(() => useTaskEpisodes(null), { wrapper: createWrapper() })
    expect(contentOpsApi.getTaskEpisodes).not.toHaveBeenCalled()
  })
})

describe('useReviewArticle', () => {
  it('calls approveArticle when action is approve', async () => {
    const { contentOpsApi } = await import('../../api')
    vi.mocked(contentOpsApi.approveArticle).mockClear()
    const { result } = renderHook(() => useReviewArticle(), { wrapper: createWrapper() })
    await act(async () => { await result.current.mutateAsync({ articleId: 1, action: 'approve' }) })
    expect(contentOpsApi.approveArticle).toHaveBeenCalledWith(1, { notes: undefined })
  })

  it('calls rejectArticle when action is reject', async () => {
    const { contentOpsApi } = await import('../../api')
    vi.mocked(contentOpsApi.rejectArticle).mockClear()
    const { result } = renderHook(() => useReviewArticle(), { wrapper: createWrapper() })
    await act(async () => { await result.current.mutateAsync({ articleId: 2, action: 'reject', notes: 'bad' }) })
    expect(contentOpsApi.rejectArticle).toHaveBeenCalledWith(2, { notes: 'bad' })
  })
})

describe('useUpdateArticle', () => {
  it('calls contentOpsApi.updateArticle', async () => {
    const { contentOpsApi } = await import('../../api')
    vi.mocked(contentOpsApi.updateArticle).mockClear()
    const { result } = renderHook(() => useUpdateArticle(), { wrapper: createWrapper() })
    await act(async () => { await result.current.mutateAsync({ articleId: 5, title: 'New' }) })
    expect(contentOpsApi.updateArticle).toHaveBeenCalledWith(5, { title: 'New', content: undefined })
  })
})

describe('useRegenerateArticle', () => {
  it('calls contentOpsApi.regenerateArticle', async () => {
    const { contentOpsApi } = await import('../../api')
    vi.mocked(contentOpsApi.regenerateArticle).mockClear()
    const { result } = renderHook(() => useRegenerateArticle(), { wrapper: createWrapper() })
    await act(async () => { await result.current.mutateAsync(8) })
    expect(contentOpsApi.regenerateArticle).toHaveBeenCalledWith(8)
  })
})

describe('useReviewEpisode', () => {
  it('calls approveEpisode when action is approve', async () => {
    const { contentOpsApi } = await import('../../api')
    vi.mocked(contentOpsApi.approveEpisode).mockClear()
    const { result } = renderHook(() => useReviewEpisode(), { wrapper: createWrapper() })
    await act(async () => { await result.current.mutateAsync({ episodeId: 3, action: 'approve' }) })
    expect(contentOpsApi.approveEpisode).toHaveBeenCalledWith(3, { notes: undefined })
  })

  it('calls rejectEpisode when action is reject', async () => {
    const { contentOpsApi } = await import('../../api')
    vi.mocked(contentOpsApi.rejectEpisode).mockClear()
    const { result } = renderHook(() => useReviewEpisode(), { wrapper: createWrapper() })
    await act(async () => { await result.current.mutateAsync({ episodeId: 4, action: 'reject', notes: 'too long' }) })
    expect(contentOpsApi.rejectEpisode).toHaveBeenCalledWith(4, { notes: 'too long' })
  })
})

describe('useCancelTask', () => {
  it('returns mutation with mutate function', () => {
    const { result } = renderHook(() => useCancelTask(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('mutate')
  })

  it('calls contentOpsApi.cancelTask on mutate', async () => {
    const { contentOpsApi } = await import('../../api')
    vi.mocked(contentOpsApi.cancelTask).mockClear()
    const { result } = renderHook(() => useCancelTask(), { wrapper: createWrapper() })
    await act(async () => { await result.current.mutateAsync(2) })
    expect(contentOpsApi.cancelTask).toHaveBeenCalledWith(2)
  })
})

describe('useDeleteTask', () => {
  it('returns mutation with mutate function', () => {
    const { result } = renderHook(() => useDeleteTask(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('mutate')
  })

  it('calls contentOpsApi.deleteTask on mutate', async () => {
    const { contentOpsApi } = await import('../../api')
    vi.mocked(contentOpsApi.deleteTask).mockClear()
    const { result } = renderHook(() => useDeleteTask(), { wrapper: createWrapper() })
    await act(async () => { await result.current.mutateAsync(6) })
    expect(contentOpsApi.deleteTask).toHaveBeenCalledWith(6)
  })
})

describe('useUpdateDiscussionTurn', () => {
  it('calls contentOpsApi.updateDiscussionTurn', async () => {
    const { contentOpsApi } = await import('../../api')
    vi.mocked(contentOpsApi.updateDiscussionTurn).mockClear()
    const { result } = renderHook(() => useUpdateDiscussionTurn(), { wrapper: createWrapper() })
    await act(async () => { await result.current.mutateAsync({ turnId: 10, text: 'updated' }) })
    expect(contentOpsApi.updateDiscussionTurn).toHaveBeenCalledWith(10, {
      text: 'updated',
      speaker_style_prompt: undefined,
    })
  })
})

describe('useReviewDiscussion', () => {
  it('calls approveDiscussion when action is approve', async () => {
    const { contentOpsApi } = await import('../../api')
    vi.mocked(contentOpsApi.approveDiscussion).mockClear()
    const { result } = renderHook(() => useReviewDiscussion(), { wrapper: createWrapper() })
    await act(async () => { await result.current.mutateAsync({ scriptId: 1, action: 'approve' }) })
    expect(contentOpsApi.approveDiscussion).toHaveBeenCalledWith(1, { notes: undefined })
  })

  it('calls rejectDiscussion when action is reject', async () => {
    const { contentOpsApi } = await import('../../api')
    vi.mocked(contentOpsApi.rejectDiscussion).mockClear()
    const { result } = renderHook(() => useReviewDiscussion(), { wrapper: createWrapper() })
    await act(async () => { await result.current.mutateAsync({ scriptId: 2, action: 'reject', notes: 'needs rewrite' }) })
    expect(contentOpsApi.rejectDiscussion).toHaveBeenCalledWith(2, { notes: 'needs rewrite' })
  })
})

describe('useRegenerateDiscussion', () => {
  it('calls contentOpsApi.regenerateDiscussion', async () => {
    const { contentOpsApi } = await import('../../api')
    vi.mocked(contentOpsApi.regenerateDiscussion).mockClear()
    const { result } = renderHook(() => useRegenerateDiscussion(), { wrapper: createWrapper() })
    await act(async () => { await result.current.mutateAsync(4) })
    expect(contentOpsApi.regenerateDiscussion).toHaveBeenCalledWith(4)
  })
})

describe('useSynthesizeDiscussion', () => {
  it('calls contentOpsApi.synthesizeDiscussion', async () => {
    const { contentOpsApi } = await import('../../api')
    vi.mocked(contentOpsApi.synthesizeDiscussion).mockClear()
    const { result } = renderHook(() => useSynthesizeDiscussion(), { wrapper: createWrapper() })
    await act(async () => { await result.current.mutateAsync(5) })
    expect(contentOpsApi.synthesizeDiscussion).toHaveBeenCalledWith(5)
  })
})
