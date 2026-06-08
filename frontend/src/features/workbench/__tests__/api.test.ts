const { mockGet, mockPost, mockJson } = vi.hoisted(() => {
  const mockJson = vi.fn().mockResolvedValue({ items: [] })
  const mockGet = vi.fn().mockReturnValue({ json: mockJson })
  const mockPost = vi.fn().mockReturnValue({ json: mockJson })
  return { mockGet, mockPost, mockJson }
})

vi.mock('@/lib/api', () => ({
  createFeatureApiClient: vi.fn(() => ({
    get: mockGet, post: mockPost,
    put: vi.fn().mockReturnValue({ json: mockJson }),
    delete: vi.fn(),
    patch: vi.fn().mockReturnValue({ json: mockJson }),
  })),
  api: { post: vi.fn().mockReturnValue({ json: mockJson }) },
  API_BASE_URL: 'http://localhost:8002/api/v1',
}))

vi.mock('@/lib/token', () => ({
  getAccessToken: vi.fn().mockReturnValue('test-token'),
}))

import { createFeatureApiClient } from '@/lib/api'

describe('workbench/api', () => {
  beforeEach(() => {
    mockGet.mockClear(); mockPost.mockClear(); mockJson.mockClear()
  })


  it('listSessions calls GET sessions', async () => {
    const api = await import('../api')
    await api.listSessions()
    expect(mockGet).toHaveBeenCalledWith('sessions', expect.any(Object))
  })

  it('createSession calls POST sessions', async () => {
    const api = await import('../api')
    await api.createSession('Test', 'gpt-4')
    expect(mockPost).toHaveBeenCalledWith('sessions', expect.any(Object))
  })

  it('listMessages calls GET sessions/:id/messages', async () => {
    const api = await import('../api')
    await api.listMessages(5, 1)
    expect(mockGet).toHaveBeenCalledWith('sessions/5/messages', expect.any(Object))
  })

  it('fetchModels calls GET models', async () => {
    const api = await import('../api')
    await api.fetchModels()
    expect(mockGet).toHaveBeenCalledWith('models')
  })
})
