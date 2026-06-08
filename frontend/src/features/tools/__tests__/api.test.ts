vi.mock('@/lib/api', () => {
  const chain = () => ({
    get: vi.fn().mockReturnThis(),
    post: vi.fn().mockReturnThis(),
    json: vi.fn().mockResolvedValue({}),
  })
  return {
    API_BASE_URL: 'http://localhost:8002/api/v1',
    createFeatureApiClient: vi.fn().mockReturnValue(chain()),
  }
})

import { expressQueryApi, lprApi_ } from '../api'
import { createFeatureApiClient } from '@/lib/api'

describe('expressQueryApi', () => {
  it('list fetches tasks', async () => {
    const client = createFeatureApiClient('express-query') as unknown as { get: ReturnType<typeof vi.fn> }
    const mockTasks = [{ id: 1, title: 'task', status: 'done' }]
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue(mockTasks) })
    const result = await expressQueryApi.list()
    expect(result).toEqual(mockTasks)
  })
})

describe('lprApi_', () => {
  it('listRates fetches with default limit', async () => {
    const client = createFeatureApiClient('lpr') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue({ items: [], total: 0 }) })
    const result = await lprApi_.listRates()
    expect(result).toEqual({ items: [], total: 0 })
  })

  it('listRates accepts custom limit', async () => {
    const client = createFeatureApiClient('lpr') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue({ items: [], total: 0 }) })
    await lprApi_.listRates(24)
    expect(client.get).toHaveBeenCalledWith('rates', { searchParams: { limit: '24' } })
  })

  it('calculate sends calculation request', async () => {
    const client = createFeatureApiClient('lpr') as unknown as { post: ReturnType<typeof vi.fn> }
    const mockResponse = { success: true, total_interest: '1000' }
    client.post.mockReturnValue({ json: vi.fn().mockResolvedValue(mockResponse) })
    const result = await lprApi_.calculate({ start_date: '2023-01-01', end_date: '2023-12-31' })
    expect(result).toEqual(mockResponse)
  })

  it('calculate handles full request body', async () => {
    const client = createFeatureApiClient('lpr') as unknown as { post: ReturnType<typeof vi.fn> }
    client.post.mockReturnValue({
      json: vi.fn().mockResolvedValue({
        success: true,
        total_interest: '500',
        periods: [],
      }),
    })
    const result = await lprApi_.calculate({
      start_date: '2023-01-01',
      end_date: '2023-06-30',
      principal: '100000',
      rate_mode: 'lpr',
      rate_type: '1y',
    })
    expect(result.success).toBe(true)
  })
})
