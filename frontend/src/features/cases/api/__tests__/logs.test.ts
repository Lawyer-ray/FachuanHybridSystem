const { mockGet, mockPost, mockPut, mockDelete, mockJson } = vi.hoisted(() => {
  const mockJson = vi.fn().mockResolvedValue([])
  const mockGet = vi.fn().mockReturnValue({ json: mockJson })
  const mockPost = vi.fn().mockReturnValue({ json: mockJson })
  const mockPut = vi.fn().mockReturnValue({ json: mockJson })
  const mockDelete = vi.fn()
  return { mockGet, mockPost, mockPut, mockDelete, mockJson }
})

vi.mock('@/lib/api', () => ({
  createFeatureApiClient: vi.fn(() => ({
    get: mockGet,
    post: mockPost,
    put: mockPut,
    delete: mockDelete,
  })),
}))

import { logsApi } from '../logs'

describe('cases/api/logsApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockJson.mockResolvedValue([])
  })

  it('list calls correct endpoint with caseId', async () => {
    await logsApi.list(1)
    expect(mockGet).toHaveBeenCalledWith('logs', { searchParams: { case_id: '1' } })
  })

  it('listAll calls correct endpoint', async () => {
    await logsApi.listAll()
    expect(mockGet).toHaveBeenCalledWith('logs')
  })

  it('create posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    const data = { case_id: 1, content: '新日志', reminder_type: 'deadline' }
    await logsApi.create(data)
    expect(mockPost).toHaveBeenCalledWith('logs', { json: data })
  })

  it('update puts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    await logsApi.update(1, { content: '更新内容' })
    expect(mockPut).toHaveBeenCalledWith('logs/1', { json: { content: '更新内容' } })
  })

  it('delete calls correct endpoint', async () => {
    await logsApi.delete(1)
    expect(mockDelete).toHaveBeenCalledWith('logs/1')
  })

  it('uploadAttachments posts with FormData', async () => {
    const file = new File(['content'], 'test.txt', { type: 'text/plain' })
    mockJson.mockResolvedValue([])
    await logsApi.uploadAttachments(1, [file])
    expect(mockPost).toHaveBeenCalledWith('logs/1/attachments', expect.objectContaining({
      body: expect.any(FormData),
    }))
  })

  it('listCaseNumbers calls correct endpoint', async () => {
    await logsApi.listCaseNumbers(1)
    expect(mockGet).toHaveBeenCalledWith('case-numbers', { searchParams: { case_id: '1' } })
  })

  it('createCaseNumber posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1, number: '(2026)京0101民初123号' })
    await logsApi.createCaseNumber({ number: '(2026)京0101民初123号' })
    expect(mockPost).toHaveBeenCalledWith('case-numbers', { json: { number: '(2026)京0101民初123号' } })
  })

  it('updateCaseNumber puts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    await logsApi.updateCaseNumber(1, { number: '新案号' })
    expect(mockPut).toHaveBeenCalledWith('case-numbers/1', { json: { number: '新案号' } })
  })

  it('deleteCaseNumber calls correct endpoint', async () => {
    await logsApi.deleteCaseNumber(1)
    expect(mockDelete).toHaveBeenCalledWith('case-numbers/1')
  })
})
