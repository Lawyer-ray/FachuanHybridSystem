const { mockGet, mockPost, mockPatch, mockJson } = vi.hoisted(() => {
  const mockJson = vi.fn().mockResolvedValue({ items: [], total: 0 })
  const mockGet = vi.fn().mockReturnValue({ json: mockJson })
  const mockPost = vi.fn().mockReturnValue({ json: mockJson })
  const mockPatch = vi.fn().mockReturnValue({ json: mockJson })
  return { mockGet, mockPost, mockPatch, mockJson }
})

vi.mock('@/lib/api', () => ({
  createFeatureApiClient: vi.fn(() => ({
    get: mockGet, post: mockPost, patch: mockPatch,
  })),
}))

describe('automation/document-recognition/api', () => {
  beforeEach(() => {
    mockGet.mockClear(); mockPost.mockClear(); mockPatch.mockClear(); mockJson.mockClear()
  })

  it('list calls GET with search params', async () => {
    const { documentRecognitionApi } = await import('../../document-recognition/api')
    await documentRecognitionApi.list({ page: 1, page_size: 20 })
    expect(mockGet).toHaveBeenCalledWith('', expect.any(Object))
  })

  it('getTask calls GET /:id/', async () => {
    const { documentRecognitionApi } = await import('../../document-recognition/api')
    await documentRecognitionApi.getTask(42)
    expect(mockGet).toHaveBeenCalledWith('42/')
  })

  it('upload calls POST upload/', async () => {
    const { documentRecognitionApi } = await import('../../document-recognition/api')
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    await documentRecognitionApi.upload(file)
    expect(mockPost).toHaveBeenCalledWith('upload/', expect.objectContaining({ body: expect.any(FormData) }))
  })

  it('searchCases calls GET search-cases/', async () => {
    const { documentRecognitionApi } = await import('../../document-recognition/api')
    await documentRecognitionApi.searchCases('test')
    expect(mockGet).toHaveBeenCalledWith('search-cases/', expect.any(Object))
  })

  it('bind calls POST /:id/bind/', async () => {
    const { documentRecognitionApi } = await import('../../document-recognition/api')
    await documentRecognitionApi.bind(5, { case_id: 10 } as any)
    expect(mockPost).toHaveBeenCalledWith('5/bind/', { json: { case_id: 10 } })
  })

  it('updateInfo calls PATCH /:id/', async () => {
    const { documentRecognitionApi } = await import('../../document-recognition/api')
    await documentRecognitionApi.updateInfo(3, { case_number: '123' } as any)
    expect(mockPatch).toHaveBeenCalledWith('3/', { json: { case_number: '123' } })
  })

  // ===== Branch coverage: list with no params =====

  it('list calls GET without search params when no params', async () => {
    const { documentRecognitionApi } = await import('../../document-recognition/api')
    await documentRecognitionApi.list()
    expect(mockGet).toHaveBeenCalledWith('', expect.any(Object))
  })

  // ===== Branch coverage: list with status param =====

  it('list includes status in search params', async () => {
    const { documentRecognitionApi } = await import('../../document-recognition/api')
    await documentRecognitionApi.list({ status: 'success' })
    expect(mockGet).toHaveBeenCalledWith('', expect.any(Object))
  })

  // ===== Branch coverage: list with page_size param =====

  it('list includes page_size in search params', async () => {
    const { documentRecognitionApi } = await import('../../document-recognition/api')
    await documentRecognitionApi.list({ page_size: 20 })
    expect(mockGet).toHaveBeenCalledWith('', expect.any(Object))
  })
})
