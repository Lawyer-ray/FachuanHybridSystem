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
    it('list with search param sets search', async () => {
      const { lawyerApi } = await import('../api')
      await lawyerApi.list({ search: '张三' })
      expect(mockGet).toHaveBeenCalledWith('lawyers', expect.objectContaining({
        searchParams: expect.any(URLSearchParams),
      }))
      const callArgs = mockGet.mock.calls[mockGet.mock.calls.length - 1]
      const sp = callArgs[1].searchParams as URLSearchParams
      expect(sp.get('search')).toBe('张三')
    })
    it('list without search does not set search param', async () => {
      const { lawyerApi } = await import('../api')
      await lawyerApi.list({})
      const callArgs = mockGet.mock.calls[mockGet.mock.calls.length - 1]
      const sp = callArgs[1].searchParams as URLSearchParams
      expect(sp.has('search')).toBe(false)
    })
    it('get calls GET lawyers/:id', async () => {
      const { lawyerApi } = await import('../api')
      await lawyerApi.get(10)
      expect(mockGet).toHaveBeenCalledWith('lawyers/10')
    })
    it('create without files calls POST with json', async () => {
      const { lawyerApi } = await import('../api')
      const data = { username: 'test', password: '123456' }
      await lawyerApi.create(data as any)
      expect(mockPost).toHaveBeenCalledWith('lawyers', { json: data })
    })
    it('create with licensePdf calls POST with FormData', async () => {
      const { lawyerApi } = await import('../api')
      const data = { username: 'test', password: '123456' }
      const pdfFile = new File(['pdf'], 'license.pdf', { type: 'application/pdf' })
      await lawyerApi.create(data as any, pdfFile)
      expect(mockPost).toHaveBeenCalledWith('lawyers', expect.objectContaining({ body: expect.any(FormData) }))
    })
    it('create with avatar only calls POST with FormData', async () => {
      const { lawyerApi } = await import('../api')
      const data = { username: 'test', password: '123456' }
      const avatarFile = new File(['img'], 'avatar.jpg', { type: 'image/jpeg' })
      await lawyerApi.create(data as any, undefined, avatarFile)
      expect(mockPost).toHaveBeenCalledWith('lawyers', expect.objectContaining({ body: expect.any(FormData) }))
    })
    it('create with both files calls POST with FormData containing both', async () => {
      const { lawyerApi } = await import('../api')
      const data = { username: 'test', password: '123456' }
      const pdfFile = new File(['pdf'], 'license.pdf', { type: 'application/pdf' })
      const avatarFile = new File(['img'], 'avatar.jpg', { type: 'image/jpeg' })
      await lawyerApi.create(data as any, pdfFile, avatarFile)
      expect(mockPost).toHaveBeenCalledWith('lawyers', expect.objectContaining({ body: expect.any(FormData) }))
    })
    it('update without files calls PUT with json', async () => {
      const { lawyerApi } = await import('../api')
      const data = { real_name: '张三' }
      await lawyerApi.update(1, data as any)
      expect(mockPut).toHaveBeenCalledWith('lawyers/1', { json: data })
    })
    it('update with licensePdf calls PUT with FormData', async () => {
      const { lawyerApi } = await import('../api')
      const data = { real_name: '张三' }
      const pdfFile = new File(['pdf'], 'license.pdf', { type: 'application/pdf' })
      await lawyerApi.update(1, data as any, pdfFile)
      expect(mockPut).toHaveBeenCalledWith('lawyers/1', expect.objectContaining({ body: expect.any(FormData) }))
    })
    it('update with avatar only calls PUT with FormData', async () => {
      const { lawyerApi } = await import('../api')
      const data = { real_name: '张三' }
      const avatarFile = new File(['img'], 'avatar.jpg', { type: 'image/jpeg' })
      await lawyerApi.update(1, data as any, undefined, avatarFile)
      expect(mockPut).toHaveBeenCalledWith('lawyers/1', expect.objectContaining({ body: expect.any(FormData) }))
    })
    it('update with both files calls PUT with FormData', async () => {
      const { lawyerApi } = await import('../api')
      const data = { real_name: '张三' }
      const pdfFile = new File(['pdf'], 'license.pdf', { type: 'application/pdf' })
      const avatarFile = new File(['img'], 'avatar.jpg', { type: 'image/jpeg' })
      await lawyerApi.update(1, data as any, pdfFile, avatarFile)
      expect(mockPut).toHaveBeenCalledWith('lawyers/1', expect.objectContaining({ body: expect.any(FormData) }))
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
    it('list with law_firm_id sets param', async () => {
      const { teamApi } = await import('../api')
      await teamApi.list({ law_firm_id: 5 })
      const callArgs = mockGet.mock.calls[mockGet.mock.calls.length - 1]
      const sp = callArgs[1].searchParams as URLSearchParams
      expect(sp.get('law_firm_id')).toBe('5')
    })
    it('list with team_type sets param', async () => {
      const { teamApi } = await import('../api')
      await teamApi.list({ team_type: 'lawyer' })
      const callArgs = mockGet.mock.calls[mockGet.mock.calls.length - 1]
      const sp = callArgs[1].searchParams as URLSearchParams
      expect(sp.get('team_type')).toBe('lawyer')
    })
    it('list with both params sets both', async () => {
      const { teamApi } = await import('../api')
      await teamApi.list({ law_firm_id: 3, team_type: 'biz' })
      const callArgs = mockGet.mock.calls[mockGet.mock.calls.length - 1]
      const sp = callArgs[1].searchParams as URLSearchParams
      expect(sp.get('law_firm_id')).toBe('3')
      expect(sp.get('team_type')).toBe('biz')
    })
    it('list with law_firm_id=0 sets param (0 is valid)', async () => {
      const { teamApi } = await import('../api')
      await teamApi.list({ law_firm_id: 0 })
      const callArgs = mockGet.mock.calls[mockGet.mock.calls.length - 1]
      const sp = callArgs[1].searchParams as URLSearchParams
      expect(sp.get('law_firm_id')).toBe('0')
    })
    it('list without law_firm_id does not set param', async () => {
      const { teamApi } = await import('../api')
      await teamApi.list({ team_type: 'lawyer' })
      const callArgs = mockGet.mock.calls[mockGet.mock.calls.length - 1]
      const sp = callArgs[1].searchParams as URLSearchParams
      expect(sp.has('law_firm_id')).toBe(false)
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
    it('update calls PUT teams/:id', async () => {
      const { teamApi } = await import('../api')
      await teamApi.update(5, { name: 'Updated' } as any)
      expect(mockPut).toHaveBeenCalledWith('teams/5', { json: { name: 'Updated' } })
    })
    it('delete calls DELETE teams/:id', async () => {
      const { teamApi } = await import('../api')
      await teamApi.delete(6)
      expect(mockDelete).toHaveBeenCalledWith('teams/6')
    })
  })

  describe('credentialApi', () => {
    it('list calls GET credentials', async () => {
      const { credentialApi } = await import('../api')
      await credentialApi.list()
      expect(mockGet).toHaveBeenCalledWith('credentials', expect.any(Object))
    })
    it('list with lawyer_id sets param', async () => {
      const { credentialApi } = await import('../api')
      await credentialApi.list({ lawyer_id: 7 })
      const callArgs = mockGet.mock.calls[mockGet.mock.calls.length - 1]
      const sp = callArgs[1].searchParams as URLSearchParams
      expect(sp.get('lawyer_id')).toBe('7')
    })
    it('list with lawyer_id=0 sets param (0 is valid)', async () => {
      const { credentialApi } = await import('../api')
      await credentialApi.list({ lawyer_id: 0 })
      const callArgs = mockGet.mock.calls[mockGet.mock.calls.length - 1]
      const sp = callArgs[1].searchParams as URLSearchParams
      expect(sp.get('lawyer_id')).toBe('0')
    })
    it('list without lawyer_id does not set param', async () => {
      const { credentialApi } = await import('../api')
      await credentialApi.list({ lawyer_name: 'test' })
      const callArgs = mockGet.mock.calls[mockGet.mock.calls.length - 1]
      const sp = callArgs[1].searchParams as URLSearchParams
      expect(sp.has('lawyer_id')).toBe(false)
    })
    it('list with lawyer_name sets param', async () => {
      const { credentialApi } = await import('../api')
      await credentialApi.list({ lawyer_name: '张三' })
      const callArgs = mockGet.mock.calls[mockGet.mock.calls.length - 1]
      const sp = callArgs[1].searchParams as URLSearchParams
      expect(sp.get('lawyer_name')).toBe('张三')
    })
    it('list without lawyer_name does not set param', async () => {
      const { credentialApi } = await import('../api')
      await credentialApi.list({ lawyer_id: 1 })
      const callArgs = mockGet.mock.calls[mockGet.mock.calls.length - 1]
      const sp = callArgs[1].searchParams as URLSearchParams
      expect(sp.has('lawyer_name')).toBe(false)
    })
    it('list with both params sets both', async () => {
      const { credentialApi } = await import('../api')
      await credentialApi.list({ lawyer_id: 3, lawyer_name: '李四' })
      const callArgs = mockGet.mock.calls[mockGet.mock.calls.length - 1]
      const sp = callArgs[1].searchParams as URLSearchParams
      expect(sp.get('lawyer_id')).toBe('3')
      expect(sp.get('lawyer_name')).toBe('李四')
    })
    it('get calls GET credentials/:id', async () => {
      const { credentialApi } = await import('../api')
      await credentialApi.get(6)
      expect(mockGet).toHaveBeenCalledWith('credentials/6')
    })
    it('create calls POST credentials', async () => {
      const { credentialApi } = await import('../api')
      const data = { lawyer_id: 1, site_name: 'test', account: 'admin', password: '123' }
      await credentialApi.create(data as any)
      expect(mockPost).toHaveBeenCalledWith('credentials', { json: data })
    })
    it('update calls PUT credentials/:id', async () => {
      const { credentialApi } = await import('../api')
      const data = { site_name: 'updated' }
      await credentialApi.update(8, data as any)
      expect(mockPut).toHaveBeenCalledWith('credentials/8', { json: data })
    })
    it('delete calls DELETE credentials/:id', async () => {
      const { credentialApi } = await import('../api')
      await credentialApi.delete(8)
      expect(mockDelete).toHaveBeenCalledWith('credentials/8')
    })
  })

  describe('default export', () => {
    it('exports all sub-APIs', async () => {
      const api = (await import('../api')).default
      expect(api).toHaveProperty('lawFirm')
      expect(api).toHaveProperty('lawyer')
      expect(api).toHaveProperty('team')
      expect(api).toHaveProperty('credential')
    })
  })
})
