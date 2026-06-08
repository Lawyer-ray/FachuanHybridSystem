/**
 * Court SMS API Tests
 * 测试法院短信 API 的参数构建和 URL 生成
 */

import { courtSmsApi } from '../api/court-sms'

vi.mock('@/lib/api', () => {
  const mockJson = vi.fn()
  const mockGet = vi.fn(() => ({ json: mockJson }))
  const mockPost = vi.fn(() => ({ json: mockJson }))
  const mockDelete = vi.fn(() => ({ json: mockJson }))
  return {
    API_BASE_URL: 'http://localhost:8002/api/v1',
    createFeatureApiClient: vi.fn(() => ({
      get: mockGet,
      post: mockPost,
      delete: mockDelete,
    })),
    __mockJson: mockJson,
    __mockGet: mockGet,
    __mockPost: mockPost,
    __mockDelete: mockDelete,
  }
})

// Re-import to get mock references
const apiModule = await import('@/lib/api')
const mockGet = (apiModule as any).__mockGet
const mockPost = (apiModule as any).__mockPost
const mockDelete = (apiModule as any).__mockDelete

beforeEach(() => {
  vi.clearAllMocks()
})

describe('courtSmsApi.downloadDocumentUrl', () => {
  it('generates correct URL with smsId and refIndex', () => {
    const url = courtSmsApi.downloadDocumentUrl(42, 3)
    expect(url).toBe('http://localhost:8002/api/v1/automation/court-sms/42/documents/3/download')
  })

  it('handles zero indices', () => {
    const url = courtSmsApi.downloadDocumentUrl(0, 0)
    expect(url).toBe('http://localhost:8002/api/v1/automation/court-sms/0/documents/0/download')
  })
})

describe('courtSmsApi.downloadAllUrl', () => {
  it('generates correct URL for downloading all documents', () => {
    const url = courtSmsApi.downloadAllUrl(99)
    expect(url).toBe('http://localhost:8002/api/v1/automation/court-sms/99/documents/download-all')
  })
})

describe('courtSmsApi.list', () => {
  it('calls GET with no params when none provided', async () => {
    await courtSmsApi.list()
    expect(mockGet).toHaveBeenCalledWith('', { searchParams: expect.any(URLSearchParams) })
    const searchParams = mockGet.mock.calls[0][1].searchParams as URLSearchParams
    expect(searchParams.toString()).toBe('')
  })

  it('passes page and page_size params', async () => {
    await courtSmsApi.list({ page: 2, page_size: 20 })
    const searchParams = mockGet.mock.calls[0][1].searchParams as URLSearchParams
    expect(searchParams.get('page')).toBe('2')
    expect(searchParams.get('page_size')).toBe('20')
  })

  it('passes status filter', async () => {
    await courtSmsApi.list({ status: 'pending' })
    const searchParams = mockGet.mock.calls[0][1].searchParams as URLSearchParams
    expect(searchParams.get('status')).toBe('pending')
  })

  it('passes sms_type filter', async () => {
    await courtSmsApi.list({ sms_type: 'court' })
    const searchParams = mockGet.mock.calls[0][1].searchParams as URLSearchParams
    expect(searchParams.get('sms_type')).toBe('court')
  })

  it('passes has_case filter', async () => {
    await courtSmsApi.list({ has_case: true })
    const searchParams = mockGet.mock.calls[0][1].searchParams as URLSearchParams
    expect(searchParams.get('has_case')).toBe('true')
  })

  it('passes date range filters', async () => {
    await courtSmsApi.list({ date_from: '2025-01-01', date_to: '2025-12-31' })
    const searchParams = mockGet.mock.calls[0][1].searchParams as URLSearchParams
    expect(searchParams.get('date_from')).toBe('2025-01-01')
    expect(searchParams.get('date_to')).toBe('2025-12-31')
  })
})

describe('courtSmsApi.get', () => {
  it('calls GET with the SMS id', async () => {
    await courtSmsApi.get(5)
    expect(mockGet).toHaveBeenCalledWith('5')
  })
})

describe('courtSmsApi.submit', () => {
  it('calls POST with content and received_at', async () => {
    await courtSmsApi.submit('SMS content', '2025-06-01T10:00:00')
    expect(mockPost).toHaveBeenCalledWith('', {
      json: { content: 'SMS content', received_at: '2025-06-01T10:00:00' },
    })
  })

  it('calls POST with content only when received_at is omitted', async () => {
    await courtSmsApi.submit('SMS content')
    expect(mockPost).toHaveBeenCalledWith('', {
      json: { content: 'SMS content', received_at: undefined },
    })
  })
})

describe('courtSmsApi.assignCase', () => {
  it('calls POST to assign-case endpoint', async () => {
    await courtSmsApi.assignCase(10, 20)
    expect(mockPost).toHaveBeenCalledWith('10/assign-case', {
      json: { case_id: 20 },
    })
  })
})

describe('courtSmsApi.retry', () => {
  it('calls POST to retry endpoint', async () => {
    await courtSmsApi.retry(7)
    expect(mockPost).toHaveBeenCalledWith('7/retry')
  })
})

describe('courtSmsApi.delete', () => {
  it('calls DELETE with the SMS id', async () => {
    await courtSmsApi.delete(3)
    expect(mockDelete).toHaveBeenCalledWith('3')
  })
})

describe('courtSmsApi.deleteBatch', () => {
  it('calls POST to batch-delete with ids', async () => {
    await courtSmsApi.deleteBatch([1, 2, 3])
    expect(mockPost).toHaveBeenCalledWith('batch-delete', {
      json: { ids: [1, 2, 3] },
    })
  })
})

describe('courtSmsApi.renameDocument', () => {
  it('calls POST to rename endpoint', async () => {
    await courtSmsApi.renameDocument(10, 0, 'new_name')
    expect(mockPost).toHaveBeenCalledWith('10/documents/0/rename', {
      json: { new_stem: 'new_name' },
    })
  })
})
