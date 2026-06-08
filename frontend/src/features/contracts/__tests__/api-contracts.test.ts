const { mockGet, mockPost, mockPut, mockDelete, mockJson } = vi.hoisted(() => {
  const mockJson = vi.fn().mockResolvedValue([])
  const mockGet = vi.fn().mockReturnValue({ json: mockJson })
  const mockPost = vi.fn().mockReturnValue({ json: mockJson })
  const mockPut = vi.fn().mockReturnValue({ json: mockJson })
  const mockDelete = vi.fn()
  return { mockGet, mockPost, mockPut, mockDelete, mockJson }
})

vi.mock('@/lib/api', () => ({
  api: { delete: mockDelete },
  createFeatureApiClient: vi.fn(() => ({
    get: mockGet, post: mockPost, put: mockPut, delete: vi.fn(),
  })),
}))

import { createFeatureApiClient, api } from '@/lib/api'

describe('contracts/api/contracts', () => {
  beforeEach(() => {
    mockGet.mockClear(); mockPost.mockClear(); mockPut.mockClear(); mockDelete.mockClear(); mockJson.mockClear()
  })


  it('list calls GET contracts', async () => {
    const { contractsApi } = await import('../api/contracts')
    await contractsApi.list()
    expect(mockGet).toHaveBeenCalledWith('contracts', expect.any(Object))
  })

  it('get calls GET contracts/:id', async () => {
    const { contractsApi } = await import('../api/contracts')
    await contractsApi.get(42)
    expect(mockGet).toHaveBeenCalledWith('contracts/42')
  })

  it('create calls POST contracts with payload wrapper', async () => {
    const { contractsApi } = await import('../api/contracts')
    const data = { title: 'Test Contract' } as any
    await contractsApi.create(data)
    expect(mockPost).toHaveBeenCalledWith('contracts', { json: { payload: data } })
  })

  it('update calls PUT contracts/:id with payload wrapper', async () => {
    const { contractsApi } = await import('../api/contracts')
    const data = { title: 'Updated' } as any
    await contractsApi.update(5, data)
    expect(mockPut).toHaveBeenCalledWith('contracts/5', { json: { payload: data } })
  })

  it('delete calls api.delete contracts/:id', async () => {
    const { contractsApi } = await import('../api/contracts')
    await contractsApi.delete(3)
    expect(api.delete).toHaveBeenCalledWith('contracts/3')
  })

  it('duplicateContract calls POST /:id/duplicate', async () => {
    const { contractsApi } = await import('../api/contracts')
    await contractsApi.duplicateContract(7)
    expect(mockPost).toHaveBeenCalledWith('7/duplicate')
  })
})
