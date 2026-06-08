const { mockGet, mockPost, mockJson } = vi.hoisted(() => {
  const mockJson = vi.fn().mockResolvedValue({ client_count: 10 })
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

import { createFeatureApiClient } from '@/lib/api'
import { getStats } from '../api'

describe('dashboard/api', () => {
  beforeEach(() => {
    mockGet.mockClear()
    mockJson.mockClear()
    mockJson.mockResolvedValue({ client_count: 10 })
  })

  it('getStats calls GET stats endpoint', async () => {
    await getStats()
    expect(mockGet).toHaveBeenCalledWith('stats')
  })

  it('getStats returns parsed JSON response', async () => {
    const result = await getStats()
    expect(result).toEqual({ client_count: 10 })
  })
})
