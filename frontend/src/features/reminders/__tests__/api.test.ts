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
    get: mockGet, post: mockPost, put: mockPut, delete: mockDelete,
  })),
}))

import { createFeatureApiClient } from '@/lib/api'

describe('reminders/api', () => {
  beforeEach(() => {
    mockGet.mockClear(); mockPost.mockClear(); mockPut.mockClear(); mockDelete.mockClear(); mockJson.mockClear()
  })

  it('list calls GET list endpoint', async () => {
    const { reminderApi } = await import('../api')
    await reminderApi.list()
    expect(mockGet).toHaveBeenCalledWith('list', expect.any(Object))
  })

  it('get calls GET /:id', async () => {
    const { reminderApi } = await import('../api')
    await reminderApi.get(42)
    expect(mockGet).toHaveBeenCalledWith('42')
  })

  it('create calls POST create with JSON body', async () => {
    const { reminderApi } = await import('../api')
    const data = { reminder_type: 'hearing' as const, content: 'Test', due_at: '2026-06-01T09:00:00Z' }
    await reminderApi.create(data)
    expect(mockPost).toHaveBeenCalledWith('create', { json: data })
  })

  it('update calls PUT /:id with JSON body', async () => {
    const { reminderApi } = await import('../api')
    const data = { reminder_type: 'hearing' as const, content: 'Updated', due_at: '2026-06-01T09:00:00Z' }
    await reminderApi.update(7, data)
    expect(mockPut).toHaveBeenCalledWith('7', { json: data })
  })

  it('delete calls DELETE /:id', async () => {
    const { reminderApi } = await import('../api')
    await reminderApi.delete(3)
    expect(mockDelete).toHaveBeenCalledWith('3')
  })

  it('getTypes calls GET types', async () => {
    const { reminderApi } = await import('../api')
    await reminderApi.getTypes()
    expect(mockGet).toHaveBeenCalledWith('types')
  })

  it('getTargetOptions calls GET target-options', async () => {
    const { reminderApi } = await import('../api')
    await reminderApi.getTargetOptions()
    expect(mockGet).toHaveBeenCalledWith('target-options', expect.any(Object))
  })
})
