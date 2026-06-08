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

import { courtFilingApi } from '../court-filing'

describe('cases/api/courtFilingApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockJson.mockResolvedValue([])
  })

  it('getCaseInfo calls correct endpoint', async () => {
    mockJson.mockResolvedValue({ case_id: 1 })
    await courtFilingApi.getCaseInfo(1)
    expect(mockGet).toHaveBeenCalledWith('case-info/1')
  })

  it('execute posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ success: true })
    const data = { case_id: 1, filing_type: 'civil' as const, filing_engine: 'api' as const }
    await courtFilingApi.execute(data)
    expect(mockPost).toHaveBeenCalledWith('execute', { json: data })
  })

  it('getSession calls correct endpoint', async () => {
    mockJson.mockResolvedValue({ status: 'done' })
    await courtFilingApi.getSession('abc-123')
    expect(mockGet).toHaveBeenCalledWith('session/abc-123')
  })
})
