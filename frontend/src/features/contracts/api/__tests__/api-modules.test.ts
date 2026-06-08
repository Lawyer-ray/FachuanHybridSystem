const { mockGet, mockPost, mockPut, mockDelete, mockJson } = vi.hoisted(() => {
  const mockJson = vi.fn().mockResolvedValue([])
  const mockGet = vi.fn().mockReturnValue({ json: mockJson, blob: vi.fn().mockResolvedValue(new Blob()) })
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

import { documentsApi } from '../documents'
import { agreementsApi } from '../agreements'
import { paymentsApi } from '../payments'

describe('contracts/api/documents', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockJson.mockResolvedValue([])
  })

  it('previewArchivePlaceholders calls correct endpoint', async () => {
    mockJson.mockResolvedValue({ success: true, data: [] })
    await documentsApi.previewArchivePlaceholders(1, 'template_sub')
    expect(mockGet).toHaveBeenCalledWith('documents/contracts/1/archive-preview', { searchParams: { template_subtype: 'template_sub' } })
  })

  it('generateContract calls download endpoint', async () => {
    await documentsApi.generateContract(5)
    expect(mockGet).toHaveBeenCalledWith('documents/contracts/5/download', { searchParams: {} })
  })

  it('generateContract passes splitFee param', async () => {
    await documentsApi.generateContract(5, true)
    expect(mockGet).toHaveBeenCalledWith('documents/contracts/5/download', { searchParams: { split_fee: 'true' } })
  })

  it('generateFolder calls blob endpoint', async () => {
    await documentsApi.generateFolder(3)
    expect(mockGet).toHaveBeenCalledWith('documents/contracts/3/folder/download')
  })

  it('generateSupplementaryAgreement calls correct endpoint', async () => {
    await documentsApi.generateSupplementaryAgreement(1, 10)
    expect(mockGet).toHaveBeenCalledWith('documents/contracts/1/supplementary-agreements/10/download')
  })
})

describe('contracts/api/agreements', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockJson.mockResolvedValue([])
  })

  it('list calls correct endpoint', async () => {
    await agreementsApi.list(1)
    expect(mockGet).toHaveBeenCalledWith('contracts/1/supplementary-agreements')
  })

  it('get calls correct endpoint', async () => {
    await agreementsApi.get(5)
    expect(mockGet).toHaveBeenCalledWith('supplementary-agreements/5')
  })

  it('create posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    const data = { contract_id: 1, name: 'Agreement' }
    await agreementsApi.create(data)
    expect(mockPost).toHaveBeenCalledWith('supplementary-agreements', { json: data })
  })

  it('update puts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 2 })
    await agreementsApi.update(2, { name: 'Updated' })
    expect(mockPut).toHaveBeenCalledWith('supplementary-agreements/2', { json: { name: 'Updated' } })
  })

  it('delete calls correct endpoint', async () => {
    await agreementsApi.delete(3)
    expect(mockDelete).toHaveBeenCalledWith('supplementary-agreements/3')
  })
})

describe('contracts/api/payments', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockJson.mockResolvedValue([])
  })

  it('list calls correct endpoint', async () => {
    await paymentsApi.list({ contract_id: 1 })
    expect(mockGet).toHaveBeenCalled()
  })

  it('create posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    const data = { amount: 1000, payment_type: 'deposit', paid_at: '2025-01-01', contract_id: 1 }
    await paymentsApi.create(data)
    expect(mockPost).toHaveBeenCalledWith('finance/payments', { json: data })
  })

  it('update calls put on correct endpoint', async () => {
    mockJson.mockResolvedValue({})
    await paymentsApi.update(2, { amount: 2000 })
    expect(mockPut).toHaveBeenCalledWith('finance/payments/2', { json: { amount: 2000 } })
  })

  it('delete calls correct endpoint', async () => {
    await paymentsApi.delete(3)
    expect(mockDelete).toHaveBeenCalledWith('finance/payments/3', { searchParams: {} })
  })

  it('getFinanceStats calls correct endpoint', async () => {
    mockJson.mockResolvedValue({ total_received: 1000 })
    await paymentsApi.getFinanceStats()
    expect(mockGet).toHaveBeenCalled()
  })
})
