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
    get: mockGet, post: mockPost, put: mockPut, delete: mockDelete,
  })),
}))

import { createFeatureApiClient } from '@/lib/api'

describe('templates/api', () => {
  beforeEach(() => {
    mockGet.mockClear(); mockPost.mockClear(); mockPut.mockClear(); mockDelete.mockClear(); mockJson.mockClear()
  })

  it('list calls GET templates', async () => {
    const { templateApi } = await import('../api')
    await templateApi.list()
    expect(mockGet).toHaveBeenCalledWith('templates')
  })

  it('get calls GET templates/:id', async () => {
    const { templateApi } = await import('../api')
    await templateApi.get(5)
    expect(mockGet).toHaveBeenCalledWith('templates/5')
  })

  it('create calls POST templates', async () => {
    const { templateApi } = await import('../api')
    await templateApi.create({ name: 'Test' })
    expect(mockPost).toHaveBeenCalledWith('templates', { json: { name: 'Test' } })
  })

  it('update calls PUT templates/:id', async () => {
    const { templateApi } = await import('../api')
    await templateApi.update(3, { name: 'Updated' })
    expect(mockPut).toHaveBeenCalledWith('templates/3', { json: { name: 'Updated' } })
  })

  it('delete calls DELETE templates/:id', async () => {
    const { templateApi } = await import('../api')
    await templateApi.delete(7)
    expect(mockDelete).toHaveBeenCalledWith('templates/7')
  })

  it('listLibraryFiles calls GET templates/library-files', async () => {
    const { templateApi } = await import('../api')
    await templateApi.listLibraryFiles()
    expect(mockGet).toHaveBeenCalledWith('templates/library-files')
  })
})
