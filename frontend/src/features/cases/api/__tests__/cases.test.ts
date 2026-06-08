const { mockGet, mockPost, mockPut, mockDelete, mockJson } = vi.hoisted(() => {
  const mockJson = vi.fn().mockResolvedValue([])
  const mockGet = vi.fn().mockReturnValue({ json: mockJson, blob: vi.fn().mockResolvedValue(new Blob()) })
  const mockPost = vi.fn().mockReturnValue({ json: mockJson })
  const mockPut = vi.fn().mockReturnValue({ json: mockJson })
  const mockDelete = vi.fn()
  return { mockGet, mockPost, mockPut, mockDelete, mockJson }
})

vi.mock('@/lib/api', () => ({
  api: { get: mockGet, post: mockPost, put: mockPut, delete: mockDelete },
  createFeatureApiClient: vi.fn(() => ({
    get: mockGet,
    post: mockPost,
    put: mockPut,
    delete: mockDelete,
  })),
}))

import { casesCrudApi } from '../cases'

describe('cases/api/casesCrudApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockJson.mockResolvedValue([])
  })

  it('list calls correct endpoint', async () => {
    mockJson.mockResolvedValue([])
    await casesCrudApi.list()
    expect(mockGet).toHaveBeenCalledWith('cases', expect.anything())
  })

  it('list passes case_type filter', async () => {
    await casesCrudApi.list({ case_type: 'litigation' })
    expect(mockGet).toHaveBeenCalledWith('cases', expect.objectContaining({
      searchParams: expect.any(URLSearchParams),
    }))
  })

  it('list passes status filter', async () => {
    await casesCrudApi.list({ status: 'active' })
    expect(mockGet).toHaveBeenCalledWith('cases', expect.objectContaining({
      searchParams: expect.any(URLSearchParams),
    }))
  })

  it('search calls correct endpoint', async () => {
    mockJson.mockResolvedValue([])
    await casesCrudApi.search('测试')
    expect(mockGet).toHaveBeenCalledWith('cases/search', expect.objectContaining({
      searchParams: expect.anything(),
    }))
  })

  it('get calls correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    await casesCrudApi.get(1)
    expect(mockGet).toHaveBeenCalledWith('cases/1')
  })

  it('create posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    await casesCrudApi.create({ name: '测试案件', case_type: 'litigation' })
    expect(mockPost).toHaveBeenCalledWith('cases', { json: { name: '测试案件', case_type: 'litigation' } })
  })

  it('createFull posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ case: { id: 1 } })
    const data = { case: { name: '测试', case_type: 'litigation' } }
    await casesCrudApi.createFull(data as any)
    expect(mockPost).toHaveBeenCalledWith('cases/full', { json: data })
  })

  it('update puts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    await casesCrudApi.update(1, { name: '更新名' })
    expect(mockPut).toHaveBeenCalledWith('cases/1', { json: { name: '更新名' } })
  })

  it('delete calls correct endpoint', async () => {
    await casesCrudApi.delete(1)
    expect(mockDelete).toHaveBeenCalledWith('cases/1')
  })

  it('searchCauses calls correct endpoint', async () => {
    mockJson.mockResolvedValue([])
    await casesCrudApi.searchCauses('合同纠纷')
    expect(mockGet).toHaveBeenCalledWith('causes-data', expect.objectContaining({
      searchParams: expect.any(URLSearchParams),
    }))
  })

  it('getCausesTree calls correct endpoint', async () => {
    mockJson.mockResolvedValue([])
    await casesCrudApi.getCausesTree()
    expect(mockGet).toHaveBeenCalledWith('causes-tree', expect.objectContaining({
      searchParams: expect.any(URLSearchParams),
    }))
  })

  it('searchCourts calls correct endpoint', async () => {
    mockJson.mockResolvedValue([])
    await casesCrudApi.searchCourts('北京市')
    expect(mockGet).toHaveBeenCalledWith('courts-data', expect.objectContaining({
      searchParams: expect.anything(),
    }))
  })

  it('calculateFee posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ amount: 5000 })
    const data = { case_type: 'litigation', amount: 100000 }
    await casesCrudApi.calculateFee(data as any)
    expect(mockPost).toHaveBeenCalledWith('calculate-fee', { json: data })
  })
})
