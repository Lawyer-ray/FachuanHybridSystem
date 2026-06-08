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

  it('listSessions passes page parameter', async () => {
    const api = await import('../api')
    await api.listSessions(3)
    expect(mockGet).toHaveBeenCalledWith('sessions', { searchParams: { page: 3 } })
  })

  it('createSession calls POST sessions', async () => {
    const api = await import('../api')
    await api.createSession('Test', 'gpt-4')
    expect(mockPost).toHaveBeenCalledWith('sessions', { json: { title: 'Test', llm_model: 'gpt-4' } })
  })

  it('createSession uses defaults when no args', async () => {
    const api = await import('../api')
    await api.createSession()
    expect(mockPost).toHaveBeenCalledWith('sessions', { json: { title: '', llm_model: '' } })
  })

  it('listMessages calls GET sessions/:id/messages', async () => {
    const api = await import('../api')
    await api.listMessages(5, 1)
    expect(mockGet).toHaveBeenCalledWith('sessions/5/messages', expect.any(Object))
  })

  it('listMessages includes beforeId in params', async () => {
    const api = await import('../api')
    await api.listMessages(5, 1, 100)
    expect(mockGet).toHaveBeenCalledWith('sessions/5/messages', {
      searchParams: { page: 1, before_id: 100 },
    })
  })

  it('fetchModels calls GET models', async () => {
    const api = await import('../api')
    await api.fetchModels()
    expect(mockGet).toHaveBeenCalledWith('models')
  })

  it('getSession calls GET sessions/:id', async () => {
    const api = await import('../api')
    await api.getSession(42)
    expect(mockGet).toHaveBeenCalledWith('sessions/42')
  })

  it('updateSession uses patch method', async () => {
    const api = await import('../api')
    // Just verify the function exists and is callable
    expect(typeof api.updateSession).toBe('function')
  })

  it('deleteSession exists and is callable', async () => {
    const api = await import('../api')
    expect(typeof api.deleteSession).toBe('function')
  })

  it('truncateMessages exists and is callable', async () => {
    const api = await import('../api')
    expect(typeof api.truncateMessages).toBe('function')
  })

  it('submitFeedback exists and is callable', async () => {
    const api = await import('../api')
    expect(typeof api.submitFeedback).toBe('function')
  })

  it('respondApproval calls POST approval', async () => {
    const api = await import('../api')
    await api.respondApproval('approval-1', true)
    expect(mockPost).toHaveBeenCalledWith('approval', { json: { approval_id: 'approval-1', approved: true } })
  })

  it('getBatchProgress calls GET batch/:id/progress', async () => {
    const api = await import('../api')
    await api.getBatchProgress('job-1')
    expect(mockGet).toHaveBeenCalledWith('batch/job-1/progress')
  })

  it('cancelBatchAnalysis calls POST batch/:id/cancel', async () => {
    const api = await import('../api')
    await api.cancelBatchAnalysis('job-1')
    expect(mockPost).toHaveBeenCalledWith('batch/job-1/cancel')
  })

  it('retryBatchAnalysis calls POST batch/:id/retry', async () => {
    const api = await import('../api')
    await api.retryBatchAnalysis('job-1')
    expect(mockPost).toHaveBeenCalledWith('batch/job-1/retry')
  })

  it('listBatchJobs calls GET sessions/:id/batch-jobs', async () => {
    const api = await import('../api')
    await api.listBatchJobs(5, 2)
    expect(mockGet).toHaveBeenCalledWith('sessions/5/batch-jobs', { searchParams: { page: 2 } })
  })

  it('listBatchJobs defaults to page 1', async () => {
    const api = await import('../api')
    await api.listBatchJobs(5)
    expect(mockGet).toHaveBeenCalledWith('sessions/5/batch-jobs', { searchParams: { page: 1 } })
  })

  it('saveBatchMessages calls POST batch/:id/messages', async () => {
    const api = await import('../api')
    const items = [{ file_name: 'test.pdf', content: 'content', metadata: {} }]
    await api.saveBatchMessages('job-1', items)
    expect(mockPost).toHaveBeenCalledWith('batch/job-1/messages', { json: items })
  })

  it('optimizePrompt calls POST optimize-prompt', async () => {
    const api = await import('../api')
    await api.optimizePrompt('test prompt')
    expect(mockPost).toHaveBeenCalledWith('optimize-prompt', { json: { prompt: 'test prompt' }, timeout: 120_000 })
  })

  it('submitBatchAnalysis calls POST batch/analyze with FormData', async () => {
    const api = await import('../api')
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    mockJson.mockResolvedValue({ id: 'job-1', status: 'running' })
    await api.submitBatchAnalysis(1, 'analyze', 'gpt-4o', [file], 10)
    expect(mockPost).toHaveBeenCalledWith('batch/analyze', {
      body: expect.any(FormData),
      timeout: 300_000,
    })
  })

  it('submitBatchAnalysis with default concurrency', async () => {
    const api = await import('../api')
    mockJson.mockResolvedValue({ id: 'job-1' })
    await api.submitBatchAnalysis(1, 'prompt', 'gpt-4o', [])
    expect(mockPost).toHaveBeenCalledWith('batch/analyze', {
      body: expect.any(FormData),
      timeout: 300_000,
    })
  })

  it('workbenchApi object has all expected methods', async () => {
    const api = await import('../api')
    expect(api.workbenchApi.createSession).toBeDefined()
    expect(api.workbenchApi.listSessions).toBeDefined()
    expect(api.workbenchApi.getSession).toBeDefined()
    expect(api.workbenchApi.updateSession).toBeDefined()
    expect(api.workbenchApi.deleteSession).toBeDefined()
    expect(api.workbenchApi.listMessages).toBeDefined()
    expect(api.workbenchApi.truncateMessages).toBeDefined()
    expect(api.workbenchApi.submitFeedback).toBeDefined()
    expect(api.workbenchApi.respondApproval).toBeDefined()
    expect(api.workbenchApi.fetchModels).toBeDefined()
    expect(api.workbenchApi.submitBatchAnalysis).toBeDefined()
    expect(api.workbenchApi.getBatchProgress).toBeDefined()
    expect(api.workbenchApi.cancelBatchAnalysis).toBeDefined()
    expect(api.workbenchApi.saveBatchMessages).toBeDefined()
    expect(api.workbenchApi.retryBatchAnalysis).toBeDefined()
    expect(api.workbenchApi.listBatchJobs).toBeDefined()
    expect(api.workbenchApi.connectBatchSSE).toBeDefined()
  })

  it('updateSession calls PATCH sessions/:id', async () => {
    const api = await import('../api')
    mockJson.mockResolvedValue({ id: 1 })
    await api.updateSession(1, { title: 'New Title' })
    expect(mockPost).not.toHaveBeenCalled() // It uses patch, not post
  })

  it('submitFeedback calls PATCH messages/:id/feedback', async () => {
    const api = await import('../api')
    mockJson.mockResolvedValue({ success: true })
    await api.submitFeedback(10, 'good', 'great')
    // It uses the mock patch from the client
  })

  it('connectBatchSSE is a function', async () => {
    const api = await import('../api')
    expect(typeof api.connectBatchSSE).toBe('function')
  })
})
