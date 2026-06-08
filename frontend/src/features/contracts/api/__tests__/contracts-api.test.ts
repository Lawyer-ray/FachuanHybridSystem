const { mockGet, mockPost, mockPut, mockDelete, mockJson } = vi.hoisted(() => {
  const mockJson = vi.fn().mockResolvedValue([])
  const mockGet = vi.fn().mockReturnValue({ json: mockJson })
  const mockPost = vi.fn().mockReturnValue({ json: mockJson })
  const mockPut = vi.fn().mockReturnValue({ json: mockJson })
  const mockDelete = vi.fn()
  return { mockGet, mockPost, mockPut, mockDelete, mockJson }
})

vi.mock('@/lib/api', () => ({
  api: {
    get: mockGet,
    post: mockPost,
    put: mockPut,
    delete: mockDelete,
  },
  createFeatureApiClient: vi.fn(() => ({
    get: mockGet,
    post: mockPost,
    put: mockPut,
    delete: mockDelete,
  })),
}))

import { contractsApi } from '../contracts'

describe('contracts/api/contracts', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockJson.mockResolvedValue([])
  })

  it('list calls correct endpoint', async () => {
    mockJson.mockResolvedValue([])
    await contractsApi.list()
    expect(mockGet).toHaveBeenCalledWith('contracts', expect.objectContaining({
      searchParams: expect.any(URLSearchParams),
    }))
  })

  it('list passes status filter', async () => {
    await contractsApi.list({ status: 'active' })
    expect(mockGet).toHaveBeenCalledWith('contracts', expect.objectContaining({
      searchParams: expect.any(URLSearchParams),
    }))
  })

  it('get calls correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    await contractsApi.get(1)
    expect(mockGet).toHaveBeenCalledWith('contracts/1')
  })

  it('create posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    const data = { name: '测试合同', case_type: 'civil', fee_mode: 'FIXED' }
    await contractsApi.create(data as any)
    expect(mockPost).toHaveBeenCalledWith('contracts', { json: { payload: data } })
  })

  it('createFull posts to full endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    const data = { name: '完整合同', case_type: 'civil' }
    await contractsApi.createFull(data as any)
    expect(mockPost).toHaveBeenCalledWith('contracts/full', { json: { payload: data } })
  })

  it('update puts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    await contractsApi.update(1, { name: '更新名' })
    expect(mockPut).toHaveBeenCalledWith('contracts/1', { json: { payload: { name: '更新名' } } })
  })

  it('delete calls correct endpoint', async () => {
    await contractsApi.delete(1)
    expect(mockDelete).toHaveBeenCalledWith('contracts/1')
  })

  it('updateLawyers puts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    await contractsApi.updateLawyers(1, [1, 2, 3])
    expect(mockPut).toHaveBeenCalledWith('contracts/1/lawyers', { json: { lawyer_ids: [1, 2, 3] } })
  })

  it('getAllParties calls correct endpoint', async () => {
    mockJson.mockResolvedValue([])
    await contractsApi.getAllParties(1)
    expect(mockGet).toHaveBeenCalledWith('contracts/1/all-parties')
  })

  it('duplicateContract posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 2 })
    await contractsApi.duplicateContract(1)
    expect(mockPost).toHaveBeenCalledWith('1/duplicate')
  })

  it('createCaseFromContract posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ case_id: 1, message: '创建成功' })
    await contractsApi.createCaseFromContract(1)
    expect(mockPost).toHaveBeenCalledWith('1/create-case')
  })

  it('renewAdvisorContract posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 2 })
    const data = { start_date: '2026-01-01', end_date: '2027-01-01' }
    await contractsApi.renewAdvisorContract(1, data)
    expect(mockPost).toHaveBeenCalledWith('1/renew', { json: data })
  })
})
