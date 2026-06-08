const { mockGet, mockPost, mockJson } = vi.hoisted(() => {
  const mockJson = vi.fn().mockResolvedValue([])
  const mockGet = vi.fn().mockReturnValue({ json: mockJson })
  const mockPost = vi.fn().mockReturnValue({ json: mockJson })
  return { mockGet, mockPost, mockJson }
})

vi.mock('@/lib/api', () => ({
  createFeatureApiClient: vi.fn(() => ({
    get: mockGet,
    post: mockPost,
  })),
}))

import { courtGuaranteeApi } from '../court-guarantee'

describe('cases/api/courtGuaranteeApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockJson.mockResolvedValue([])
  })

  it('getCaseInfo calls correct endpoint', async () => {
    mockJson.mockResolvedValue({ case_id: 1 })
    await courtGuaranteeApi.getCaseInfo(1)
    expect(mockGet).toHaveBeenCalledWith('case-info/1')
  })

  it('ensureQuote posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ quote_id: 1, status: 'done' })
    const data = { case_id: 1, insurer_id: 'ins-1' }
    await courtGuaranteeApi.ensureQuote(data)
    expect(mockPost).toHaveBeenCalledWith('quote/ensure', { json: data })
  })

  it('bindQuote posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ success: true })
    await courtGuaranteeApi.bindQuote(5)
    expect(mockPost).toHaveBeenCalledWith('quote/5/bind', { json: {} })
  })

  it('retryQuote posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ quote_id: 5, status: 'retrying' })
    await courtGuaranteeApi.retryQuote(5)
    expect(mockPost).toHaveBeenCalledWith('quote/5/retry', { json: {} })
  })

  it('deleteQuote posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ success: true })
    await courtGuaranteeApi.deleteQuote(5)
    expect(mockPost).toHaveBeenCalledWith('quote/5/delete', { json: {} })
  })

  it('deleteQuoteBinding posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ success: true })
    await courtGuaranteeApi.deleteQuoteBinding(3)
    expect(mockPost).toHaveBeenCalledWith('quote-binding/3/delete', { json: {} })
  })

  it('execute posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ session_id: 'abc', status: 'started' })
    await courtGuaranteeApi.execute(1)
    expect(mockPost).toHaveBeenCalledWith('execute', { json: { case_id: 1 } })
  })

  it('getSession calls correct endpoint', async () => {
    mockJson.mockResolvedValue({ session_id: 'abc', status: 'done' })
    await courtGuaranteeApi.getSession('abc-123')
    expect(mockGet).toHaveBeenCalledWith('session/abc-123')
  })
})
