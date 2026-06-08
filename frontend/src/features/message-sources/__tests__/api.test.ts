const { mockGet, mockPost, mockPut, mockDelete, mockJson } = vi.hoisted(() => {
  const mockJson = vi.fn().mockResolvedValue([])
  const mockGet = vi.fn().mockReturnValue({ json: mockJson })
  const mockPost = vi.fn().mockReturnValue({ json: mockJson })
  const mockPut = vi.fn().mockReturnValue({ json: mockJson })
  const mockDelete = vi.fn()
  return { mockGet, mockPost, mockPut, mockDelete, mockJson }
})

vi.mock('@/lib/api', () => ({
  createFeatureApiClient: vi.fn(() => ({
    get: mockGet,
    post: mockPost,
    put: mockPut,
    delete: mockDelete,
  })),
}))

import { createFeatureApiClient } from '@/lib/api'

describe('message-sources/api', () => {
  beforeEach(() => {
    mockGet.mockClear()
    mockPost.mockClear()
    mockPut.mockClear()
    mockDelete.mockClear()
    mockJson.mockClear()
  })

  it('list calls GET sources endpoint', async () => {
    const { messageSourceApi } = await import('../api')
    await messageSourceApi.list()
    expect(mockGet).toHaveBeenCalledWith('sources')
  })

  it('get calls GET sources/:id endpoint', async () => {
    const { messageSourceApi } = await import('../api')
    await messageSourceApi.get(42)
    expect(mockGet).toHaveBeenCalledWith('sources/42')
  })

  it('create calls POST sources with JSON body', async () => {
    const { messageSourceApi } = await import('../api')
    const data = { display_name: 'Test', source_type: 'imap', credential_id: 1 }
    await messageSourceApi.create(data)
    expect(mockPost).toHaveBeenCalledWith('sources', { json: data })
  })

  it('update calls PUT sources/:id with JSON body', async () => {
    const { messageSourceApi } = await import('../api')
    await messageSourceApi.update(5, { display_name: 'Updated' })
    expect(mockPut).toHaveBeenCalledWith('sources/5', { json: { display_name: 'Updated' } })
  })

  it('delete calls DELETE sources/:id', async () => {
    const { messageSourceApi } = await import('../api')
    await messageSourceApi.delete(3)
    expect(mockDelete).toHaveBeenCalledWith('sources/3')
  })

  it('sync calls POST sources/:id/sync', async () => {
    const { messageSourceApi } = await import('../api')
    await messageSourceApi.sync(7)
    expect(mockPost).toHaveBeenCalledWith('sources/7/sync')
  })

  it('syncAll calls POST sources/sync-all', async () => {
    const { messageSourceApi } = await import('../api')
    await messageSourceApi.syncAll()
    expect(mockPost).toHaveBeenCalledWith('sources/sync-all')
  })
})
