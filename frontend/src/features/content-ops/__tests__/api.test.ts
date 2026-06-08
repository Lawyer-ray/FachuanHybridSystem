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
})
