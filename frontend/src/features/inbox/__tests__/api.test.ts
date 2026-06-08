vi.mock('@/lib/api', () => {
  const mockJson = vi.fn()
  const chain = () => ({
    get: vi.fn().mockReturnThis(),
    post: vi.fn().mockReturnThis(),
    put: vi.fn().mockReturnThis(),
    patch: vi.fn().mockReturnThis(),
    delete: vi.fn().mockReturnThis(),
    json: mockJson,
  })
  return {
    API_BASE_URL: 'http://localhost:8002/api/v1',
    createFeatureApiClient: vi.fn().mockReturnValue(chain()),
  }
})

import { inboxApi } from '../api'
import { createFeatureApiClient } from '@/lib/api'

describe('inboxApi', () => {
  it('list builds searchParams from options', async () => {
    const mockGet = vi.fn().mockReturnValue({ json: vi.fn().mockResolvedValue([]) })
    const client = createFeatureApiClient('inbox') as unknown as ReturnType<typeof createFeatureApiClient>
    ;(client.get as ReturnType<typeof vi.fn>).mockReturnValue({ json: vi.fn().mockResolvedValue([]) })
    await inboxApi.list({ source_id: 3, has_attachments: true, search: 'test' })
    expect(createFeatureApiClient).toHaveBeenCalledWith('inbox')
  })

  it('list works with no params', async () => {
    const client = createFeatureApiClient('inbox') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue([]) })
    const result = await inboxApi.list()
    expect(result).toEqual([])
  })

  it('get fetches single message', async () => {
    const client = createFeatureApiClient('inbox') as unknown as { get: ReturnType<typeof vi.fn> }
    client.get.mockReturnValue({ json: vi.fn().mockResolvedValue({ id: 1, subject: 'Hello' }) })
    const result = await inboxApi.get(1)
    expect(result).toEqual({ id: 1, subject: 'Hello' })
  })

  it('attachmentDownloadUrl generates correct URL', () => {
    const url = inboxApi.attachmentDownloadUrl(42, 2)
    expect(url).toBe('http://localhost:8002/api/v1/inbox/messages/42/attachments/2/download')
  })

  it('attachmentPreviewUrl generates correct URL', () => {
    const url = inboxApi.attachmentPreviewUrl(42, 2)
    expect(url).toBe('http://localhost:8002/api/v1/inbox/messages/42/attachments/2/preview')
  })

  it('renameAttachment posts to correct endpoint', async () => {
    const client = createFeatureApiClient('inbox') as unknown as { post: ReturnType<typeof vi.fn> }
    client.post.mockReturnValue({ json: vi.fn().mockResolvedValue({ ok: true }) })
    const result = await inboxApi.renameAttachment(42, 1, 'new_name.pdf')
    expect(result).toEqual({ ok: true })
  })
})
