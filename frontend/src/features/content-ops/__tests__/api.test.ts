const { mockGet, mockPost, mockPut, mockDelete, mockJson } = vi.hoisted(() => {
  const mockJson = vi.fn().mockResolvedValue([])
  const mockGet = vi.fn().mockReturnValue({ json: mockJson })
  const mockPost = vi.fn().mockReturnValue({ json: mockJson })
  const mockPut = vi.fn().mockReturnValue({ json: mockJson })
  const mockDelete = vi.fn().mockReturnValue({ json: mockJson })
  return { mockGet, mockPost, mockPut, mockDelete, mockJson }
})

vi.mock('@/lib/api', () => ({
  createFeatureApiClient: vi.fn(() => ({
    get: mockGet, post: mockPost, put: mockPut, delete: mockDelete,
  })),
  resolveMediaUrl: vi.fn((url: string) => `http://localhost:8002${url}`),
}))

vi.mock('@/lib/token', () => ({
  getAccessToken: vi.fn().mockReturnValue('test-token'),
}))

import { createFeatureApiClient } from '@/lib/api'

describe('content-ops/api', () => {
  beforeEach(() => {
    mockGet.mockClear(); mockPost.mockClear(); mockJson.mockClear()
  })

  it('listTasks calls GET tasks', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.listTasks()
    expect(mockGet).toHaveBeenCalledWith('tasks', expect.any(Object))
  })

  it('getTask calls GET tasks/:id', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.getTask(42)
    expect(mockGet).toHaveBeenCalledWith('tasks/42')
  })

  it('createTask calls POST tasks', async () => {
    const { contentOpsApi } = await import('../api')
    const data = { topic: 'Test', model: 'gpt-4' }
    await contentOpsApi.createTask(data as any)
    expect(mockPost).toHaveBeenCalledWith('tasks', { json: data })
  })

  it('deleteTask calls DELETE tasks/:id', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.deleteTask(5)
    expect(mockDelete).toHaveBeenCalledWith('tasks/5')
  })

  it('getAudioUrl returns URL with token', async () => {
    const { contentOpsApi } = await import('../api')
    const url = contentOpsApi.getAudioUrl(10)
    expect(url).toContain('/api/v1/content-ops/episodes/10/audio')
    expect(url).toContain('token=test-token')
  })

  it('suggestTopics calls POST topics/suggest with timeout', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.suggestTopics()
    expect(mockPost).toHaveBeenCalledWith('topics/suggest', expect.objectContaining({
      json: expect.any(Object), timeout: 120_000,
    }))
  })

  it('getHotTopics calls GET topics/hot', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.getHotTopics()
    expect(mockGet).toHaveBeenCalledWith('topics/hot', expect.any(Object))
  })

  it('getHotTopics passes source parameter', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.getHotTopics('legaltech')
    expect(mockGet).toHaveBeenCalledWith('topics/hot', expect.objectContaining({
      searchParams: { source: 'legaltech' },
      timeout: 120_000,
    }))
  })

  it('refreshHotTopics calls POST topics/hot/refresh', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.refreshHotTopics()
    expect(mockPost).toHaveBeenCalledWith('topics/hot/refresh', expect.objectContaining({
      json: { source: '' },
    }))
  })

  it('refreshHotTopics passes source param with legaltech timeout', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.refreshHotTopics('legaltech')
    expect(mockPost).toHaveBeenCalledWith('topics/hot/refresh', expect.objectContaining({
      json: { source: 'legaltech' },
      timeout: 120_000,
    }))
  })

  it('getInspiration calls POST topics/inspiration with timeout', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.getInspiration('gpt-4')
    expect(mockPost).toHaveBeenCalledWith('topics/inspiration', expect.objectContaining({
      json: { model: 'gpt-4' },
      timeout: 120_000,
    }))
  })

  it('translateTopics calls POST topics/translate', async () => {
    const { contentOpsApi } = await import('../api')
    mockJson.mockResolvedValueOnce({ translations: ['a', 'b'] })
    await contentOpsApi.translateTopics(['title1', 'title2'])
    expect(mockPost).toHaveBeenCalledWith('topics/translate', expect.objectContaining({
      json: { titles: ['title1', 'title2'] },
      timeout: 120_000,
    }))
  })

  it('retryTask calls POST tasks/:id/retry', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.retryTask(5)
    expect(mockPost).toHaveBeenCalledWith('tasks/5/retry')
  })

  it('cancelTask calls POST tasks/:id/cancel', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.cancelTask(3)
    expect(mockPost).toHaveBeenCalledWith('tasks/3/cancel')
  })

  it('getTaskArticles calls GET tasks/:id/articles', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.getTaskArticles(7)
    expect(mockGet).toHaveBeenCalledWith('tasks/7/articles')
  })

  it('getTaskEpisodes calls GET tasks/:id/episodes', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.getTaskEpisodes(9)
    expect(mockGet).toHaveBeenCalledWith('tasks/9/episodes')
  })

  it('getTaskDiscussions calls GET tasks/:id/discussions', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.getTaskDiscussions(11)
    expect(mockGet).toHaveBeenCalledWith('tasks/11/discussions')
  })

  it('getDiscussion calls GET discussions/:id', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.getDiscussion(4)
    expect(mockGet).toHaveBeenCalledWith('discussions/4')
  })

  it('updateDiscussionTurn calls PUT discussions/turns/:id', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.updateDiscussionTurn(6, { text: 'hello' })
    expect(mockPut).toHaveBeenCalledWith('discussions/turns/6', { json: { text: 'hello' } })
  })

  it('approveDiscussion calls POST discussions/:id/approve', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.approveDiscussion(2)
    expect(mockPost).toHaveBeenCalledWith('discussions/2/approve', { json: {} })
  })

  it('rejectDiscussion calls POST discussions/:id/reject', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.rejectDiscussion(2, { notes: 'bad' })
    expect(mockPost).toHaveBeenCalledWith('discussions/2/reject', { json: { notes: 'bad' } })
  })

  it('regenerateDiscussion calls POST discussions/:id/regenerate', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.regenerateDiscussion(3)
    expect(mockPost).toHaveBeenCalledWith('discussions/3/regenerate')
  })

  it('synthesizeDiscussion calls POST discussions/:id/synthesize', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.synthesizeDiscussion(3)
    expect(mockPost).toHaveBeenCalledWith('discussions/3/synthesize', { timeout: 600_000 })
  })

  it('approveArticle calls POST articles/:id/approve', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.approveArticle(10)
    expect(mockPost).toHaveBeenCalledWith('articles/10/approve', { json: {} })
  })

  it('rejectArticle calls POST articles/:id/reject with notes', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.rejectArticle(10, { notes: 'needs edit' })
    expect(mockPost).toHaveBeenCalledWith('articles/10/reject', { json: { notes: 'needs edit' } })
  })

  it('updateArticle calls PUT articles/:id', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.updateArticle(10, { title: 'New Title' })
    expect(mockPut).toHaveBeenCalledWith('articles/10', { json: { title: 'New Title' } })
  })

  it('regenerateArticle calls POST articles/:id/regenerate', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.regenerateArticle(10)
    expect(mockPost).toHaveBeenCalledWith('articles/10/regenerate')
  })

  it('batchApproveArticles calls POST articles/batch/approve', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.batchApproveArticles([1, 2, 3], 'good')
    expect(mockPost).toHaveBeenCalledWith('articles/batch/approve', {
      json: { ids: [1, 2, 3], notes: 'good' },
    })
  })

  it('batchApproveArticles uses empty notes when omitted', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.batchApproveArticles([1])
    expect(mockPost).toHaveBeenCalledWith('articles/batch/approve', {
      json: { ids: [1], notes: '' },
    })
  })

  it('batchApproveEpisodes calls POST episodes/batch/approve', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.batchApproveEpisodes([5, 6])
    expect(mockPost).toHaveBeenCalledWith('episodes/batch/approve', {
      json: { ids: [5, 6], notes: '' },
    })
  })

  it('approveEpisode calls POST episodes/:id/approve', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.approveEpisode(8)
    expect(mockPost).toHaveBeenCalledWith('episodes/8/approve', { json: {} })
  })

  it('rejectEpisode calls POST episodes/:id/reject', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.rejectEpisode(8, { notes: 'too long' })
    expect(mockPost).toHaveBeenCalledWith('episodes/8/reject', { json: { notes: 'too long' } })
  })

  it('getAudioUrl returns null when resolveMediaUrl returns falsy', async () => {
    const { resolveMediaUrl } = await import('@/lib/api')
    vi.mocked(resolveMediaUrl).mockReturnValueOnce('')
    const { contentOpsApi } = await import('../api')
    const url = contentOpsApi.getAudioUrl(1)
    expect(url).toBeNull()
  })

  it('getAudioUrl returns URL without token when no access token', async () => {
    const { getAccessToken } = await import('@/lib/token')
    vi.mocked(getAccessToken).mockReturnValueOnce('')
    const { contentOpsApi } = await import('../api')
    const url = contentOpsApi.getAudioUrl(20)
    expect(url).toContain('/api/v1/content-ops/episodes/20/audio')
    expect(url).not.toContain('token=')
  })

  it('suggestTopics uses default empty model when omitted', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.suggestTopics()
    expect(mockPost).toHaveBeenCalledWith('topics/suggest', expect.objectContaining({
      json: { model: '' },
    }))
  })

  it('listTasks includes mode in searchParams', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.listTasks('manual')
    expect(mockGet).toHaveBeenCalledWith('tasks', expect.objectContaining({
      searchParams: { mode: 'manual' },
    }))
  })

  it('listTasks omits searchParams when no mode', async () => {
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.listTasks()
    expect(mockGet).toHaveBeenCalledWith('tasks', expect.objectContaining({
      searchParams: undefined,
    }))
  })

  it('testTts calls POST tts/test and returns blob', async () => {
    const mockBlob = vi.fn().mockResolvedValue(new Blob())
    mockPost.mockReturnValueOnce({ blob: mockBlob })
    const { contentOpsApi } = await import('../api')
    await contentOpsApi.testTts('hello', 'zh-CN', 'calm')
    expect(mockPost).toHaveBeenCalledWith('tts/test', {
      json: { text: 'hello', voice: 'zh-CN', audio_format: 'mp3', style_prompt: 'calm' },
    })
  })
})
