const { mockGet, mockPost, mockJson } = vi.hoisted(() => {
  const mockJson = vi.fn().mockResolvedValue({ items: [], total: 0 })
  const mockGet = vi.fn().mockReturnValue({ json: mockJson })
  const mockPost = vi.fn().mockReturnValue({ json: mockJson })
  return { mockGet, mockPost, mockJson }
})

vi.mock('@/lib/api', () => ({
  createFeatureApiClient: vi.fn(() => ({
    get: mockGet, post: mockPost,
  })),
}))

import { createFeatureApiClient } from '@/lib/api'

describe('automation/preservation-quotes/api', () => {
  beforeEach(() => {
    mockGet.mockClear(); mockPost.mockClear(); mockJson.mockClear()
  })


  it('list calls GET with search params', async () => {
    const { preservationQuoteApi } = await import('../api')
    await preservationQuoteApi.list({ page: 1, page_size: 20 })
    expect(mockGet).toHaveBeenCalledWith('', expect.any(Object))
  })

  it('get calls GET /:id/', async () => {
    const { preservationQuoteApi } = await import('../api')
    await preservationQuoteApi.get(42)
    expect(mockGet).toHaveBeenCalledWith('42/')
  })

  it('create calls POST with JSON body', async () => {
    const { preservationQuoteApi } = await import('../api')
    const data = { preserve_amount: 100000 } as any
    await preservationQuoteApi.create(data)
    expect(mockPost).toHaveBeenCalledWith('', { json: data })
  })

  it('execute calls POST /:id/execute/', async () => {
    const { preservationQuoteApi } = await import('../api')
    await preservationQuoteApi.execute(5)
    expect(mockPost).toHaveBeenCalledWith('5/execute/')
  })

  it('retry calls POST /:id/retry/', async () => {
    const { preservationQuoteApi } = await import('../api')
    await preservationQuoteApi.retry(3)
    expect(mockPost).toHaveBeenCalledWith('3/retry/')
  })
})
