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

describe('organization/api', () => {
  beforeEach(() => {
    mockGet.mockClear(); mockPost.mockClear(); mockPut.mockClear(); mockDelete.mockClear(); mockJson.mockClear()
  })

  describe('lawFirmApi', () => {
    it('list calls GET lawfirms', async () => {
      const { lawFirmApi } = await import('../api')
      await lawFirmApi.list()
      expect(mockGet).toHaveBeenCalledWith('lawfirms')
    })
    it('get calls GET lawfirms/:id', async () => {
      const { lawFirmApi } = await import('../api')
      await lawFirmApi.get(5)
      expect(mockGet).toHaveBeenCalledWith('lawfirms/5')
    })
    it('create calls POST lawfirms', async () => {
      const { lawFirmApi } = await import('../api')
      await lawFirmApi.create({ name: 'Test' } as any)
      expect(mockPost).toHaveBeenCalledWith('lawfirms', { json: { name: 'Test' } })
    })
    it('update calls PUT lawfirms/:id', async () => {
      const { lawFirmApi } = await import('../api')
      await lawFirmApi.update(3, { name: 'Updated' } as any)
      expect(mockPut).toHaveBeenCalledWith('lawfirms/3', { json: { name: 'Updated' } })
    })
    it('delete calls DELETE lawfirms/:id', async () => {
      const { lawFirmApi } = await import('../api')
      await lawFirmApi.delete(7)
      expect(mockDelete).toHaveBeenCalledWith('lawfirms/7')
    })
  })

  describe('lawyerApi', () => {
    it('list calls GET lawyers', async () => {
      const { lawyerApi } = await import('../api')
      await lawyerApi.list()
      expect(mockGet).toHaveBeenCalledWith('lawyers', expect.any(Object))
    })
    it('get calls GET lawyers/:id', async () => {
      const { lawyerApi } = await import('../api')
      await lawyerApi.get(10)
      expect(mockGet).toHaveBeenCalledWith('lawyers/10')
    })
    it('delete calls DELETE lawyers/:id', async () => {
      const { lawyerApi } = await import('../api')
      await lawyerApi.delete(2)
      expect(mockDelete).toHaveBeenCalledWith('lawyers/2')
    })
  })

  describe('teamApi', () => {
    it('list calls GET teams', async () => {
      const { teamApi } = await import('../api')
      await teamApi.list()
      expect(mockGet).toHaveBeenCalledWith('teams', expect.any(Object))
    })
    it('get calls GET teams/:id', async () => {
      const { teamApi } = await import('../api')
      await teamApi.get(4)
      expect(mockGet).toHaveBeenCalledWith('teams/4')
    })
    it('create calls POST teams', async () => {
      const { teamApi } = await import('../api')
      await teamApi.create({ name: 'Team A' } as any)
      expect(mockPost).toHaveBeenCalledWith('teams', { json: { name: 'Team A' } })
    })
  })

  describe('credentialApi', () => {
    it('list calls GET credentials', async () => {
      const { credentialApi } = await import('../api')
      await credentialApi.list()
      expect(mockGet).toHaveBeenCalledWith('credentials', expect.any(Object))
    })
    it('get calls GET credentials/:id', async () => {
      const { credentialApi } = await import('../api')
      await credentialApi.get(6)
      expect(mockGet).toHaveBeenCalledWith('credentials/6')
    })
    it('delete calls DELETE credentials/:id', async () => {
      const { credentialApi } = await import('../api')
      await credentialApi.delete(8)
      expect(mockDelete).toHaveBeenCalledWith('credentials/8')
    })
  })
})
