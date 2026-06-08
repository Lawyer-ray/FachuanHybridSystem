vi.mock('@/lib/api', () => {
  const chain = () => ({
    get: vi.fn().mockReturnThis(),
    post: vi.fn().mockReturnThis(),
    put: vi.fn().mockReturnThis(),
    delete: vi.fn().mockResolvedValue(undefined),
    json: vi.fn().mockResolvedValue({}),
  })
  return {
    API_BASE_URL: 'http://localhost:8002/api/v1',
    createFeatureApiClient: vi.fn().mockReturnValue(chain()),
  }
})

import { contactApi } from '../api'
import { createFeatureApiClient } from '@/lib/api'

describe('contactApi', () => {
  it('list fetches contacts with case_id', async () => {
    const client = createFeatureApiClient('contacts') as unknown as { get: ReturnType<typeof vi.fn> }
    const mockContacts = [{ id: 1, name: 'Judge Li' }]
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue(mockContacts) })
    const result = await contactApi.list(42)
    expect(result).toEqual(mockContacts)
  })

  it('list includes stage param when provided', async () => {
    const client = createFeatureApiClient('contacts') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue([]) })
    await contactApi.list(42, 'filing')
    expect(client.get).toHaveBeenCalled()
  })

  it('create sends new contact data', async () => {
    const client = createFeatureApiClient('contacts') as unknown as { post: ReturnType<typeof vi.fn> }
    const mockContact = { id: 1, name: 'Judge Wang', role: 'judge' }
    client.post.mockReturnValue({ json: vi.fn().mockResolvedValue(mockContact) })
    const result = await contactApi.create({ case_id: 1, name: 'Judge Wang', role: 'judge' })
    expect(result).toEqual(mockContact)
  })

  it('update sends partial contact data', async () => {
    const client = createFeatureApiClient('contacts') as unknown as { put: ReturnType<typeof vi.fn> }
    client.put.mockReturnValue({ json: vi.fn().mockResolvedValue({ id: 1, name: 'Updated' }) })
    const result = await contactApi.update(1, { name: 'Updated' })
    expect(result).toEqual({ id: 1, name: 'Updated' })
  })

  it('delete removes contact by id', async () => {
    const client = createFeatureApiClient('contacts') as unknown as { delete: ReturnType<typeof vi.fn> }
    client.delete.mockResolvedValue(undefined)
    await contactApi.delete(5)
    expect(client.delete).toHaveBeenCalledWith('contacts/5')
  })

  it('search sends query params', async () => {
    const client = createFeatureApiClient('contacts') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue([]) })
    const result = await contactApi.search({ q: 'wang', court: 'beijing', role: 'judge', limit: 10 })
    expect(result).toEqual([])
  })
})
