vi.mock('@/lib/api', () => {
  const mockJson = vi.fn()
  const mockGet = vi.fn(() => ({ json: mockJson }))
  const mockPost = vi.fn(() => ({ json: mockJson }))
  const mockPut = vi.fn(() => ({ json: mockJson }))
  return {
    api: { delete: vi.fn() },
    createFeatureApiClient: () => ({
      get: mockGet,
      post: mockPost,
      put: mockPut,
    }),
    __mocks: { mockGet, mockPost, mockPut, mockJson },
  }
})

import { api } from '@/lib/api'
import { paymentsApi } from '../api/payments'

// Get the mocks from the module
const mod = await import('@/lib/api')
const { mockGet, mockPost, mockPut, mockJson } = (mod as unknown as { __mocks: { mockGet: ReturnType<typeof vi.fn>; mockPost: ReturnType<typeof vi.fn>; mockPut: ReturnType<typeof vi.fn>; mockJson: ReturnType<typeof vi.fn> } }).__mocks

describe('paymentsApi', () => {
  beforeEach(() => {
    mockGet.mockClear()
    mockPost.mockClear()
    mockPut.mockClear()
    mockJson.mockReset()
    mockJson.mockResolvedValue([])
    vi.mocked(api.delete).mockReset()
  })

  describe('list', () => {
    it('calls GET with no params', async () => {
      const result = await paymentsApi.list()
      expect(mockGet).toHaveBeenCalledWith('finance/payments', expect.objectContaining({ searchParams: expect.any(URLSearchParams) }))
      expect(result).toEqual([])
    })

    it('sets contract_id param when provided', async () => {
      await paymentsApi.list({ contract_id: 42 })
      const sp = mockGet.mock.calls[0][1].searchParams as URLSearchParams
      expect(sp.get('contract_id')).toBe('42')
    })

    it('sets invoice_status param when provided', async () => {
      await paymentsApi.list({ invoice_status: 'INVOICED_FULL' })
      const sp = mockGet.mock.calls[0][1].searchParams as URLSearchParams
      expect(sp.get('invoice_status')).toBe('INVOICED_FULL')
    })

    it('sets start_date param when provided', async () => {
      await paymentsApi.list({ start_date: '2024-01-01' })
      const sp = mockGet.mock.calls[0][1].searchParams as URLSearchParams
      expect(sp.get('start_date')).toBe('2024-01-01')
    })

    it('sets end_date param when provided', async () => {
      await paymentsApi.list({ end_date: '2024-12-31' })
      const sp = mockGet.mock.calls[0][1].searchParams as URLSearchParams
      expect(sp.get('end_date')).toBe('2024-12-31')
    })

    it('sets all params when all provided', async () => {
      await paymentsApi.list({ contract_id: 1, invoice_status: 'UNINVOICED', start_date: '2024-01-01', end_date: '2024-12-31' })
      const sp = mockGet.mock.calls[0][1].searchParams as URLSearchParams
      expect(sp.get('contract_id')).toBe('1')
      expect(sp.get('invoice_status')).toBe('UNINVOICED')
      expect(sp.get('start_date')).toBe('2024-01-01')
      expect(sp.get('end_date')).toBe('2024-12-31')
    })

    it('does not set contract_id when undefined', async () => {
      await paymentsApi.list({})
      const sp = mockGet.mock.calls[0][1].searchParams as URLSearchParams
      expect(sp.has('contract_id')).toBe(false)
    })

    it('does not set invoice_status when empty string', async () => {
      await paymentsApi.list({ invoice_status: '' })
      const sp = mockGet.mock.calls[0][1].searchParams as URLSearchParams
      expect(sp.has('invoice_status')).toBe(false)
    })

    it('does not set start_date when undefined', async () => {
      await paymentsApi.list({})
      const sp = mockGet.mock.calls[0][1].searchParams as URLSearchParams
      expect(sp.has('start_date')).toBe(false)
    })

    it('does not set end_date when undefined', async () => {
      await paymentsApi.list({})
      const sp = mockGet.mock.calls[0][1].searchParams as URLSearchParams
      expect(sp.has('end_date')).toBe(false)
    })
  })

  describe('create', () => {
    it('posts payment data', async () => {
      mockJson.mockResolvedValue({ id: 1, amount: 10000 })
      const result = await paymentsApi.create({ contract_id: 1, amount: 10000 })
      expect(mockPost).toHaveBeenCalledWith('finance/payments', { json: { contract_id: 1, amount: 10000 } })
      expect(result).toEqual({ id: 1, amount: 10000 })
    })
  })

  describe('update', () => {
    it('puts payment data', async () => {
      mockJson.mockResolvedValue({ id: 1, amount: 20000 })
      const result = await paymentsApi.update(1, { amount: 20000 })
      expect(mockPut).toHaveBeenCalledWith('finance/payments/1', { json: { amount: 20000 } })
      expect(result).toEqual({ id: 1, amount: 20000 })
    })
  })

  describe('delete', () => {
    it('deletes payment without confirm', async () => {
      vi.mocked(api.delete).mockResolvedValue(undefined as never)
      await paymentsApi.delete(1)
      expect(api.delete).toHaveBeenCalledWith('finance/payments/1', { searchParams: {} })
    })

    it('deletes payment with confirm', async () => {
      vi.mocked(api.delete).mockResolvedValue(undefined as never)
      await paymentsApi.delete(1, true)
      expect(api.delete).toHaveBeenCalledWith('finance/payments/1', { searchParams: { confirm: 'true' } })
    })

    it('deletes payment with confirm=false', async () => {
      vi.mocked(api.delete).mockResolvedValue(undefined as never)
      await paymentsApi.delete(1, false)
      expect(api.delete).toHaveBeenCalledWith('finance/payments/1', { searchParams: {} })
    })
  })

  describe('getFinanceStats', () => {
    it('calls GET with no params', async () => {
      mockJson.mockResolvedValue({ items: [], total_received_all: 0, total_invoiced_all: 0 })
      const result = await paymentsApi.getFinanceStats()
      expect(mockGet).toHaveBeenCalledWith('finance/stats', expect.objectContaining({ searchParams: expect.any(URLSearchParams) }))
      expect(result).toEqual({ items: [], total_received_all: 0, total_invoiced_all: 0 })
    })

    it('sets contract_id param when provided', async () => {
      mockJson.mockResolvedValue({ items: [] })
      await paymentsApi.getFinanceStats({ contract_id: 5 })
      const sp = mockGet.mock.calls[0][1].searchParams as URLSearchParams
      expect(sp.get('contract_id')).toBe('5')
    })

    it('sets start_date param when provided', async () => {
      mockJson.mockResolvedValue({ items: [] })
      await paymentsApi.getFinanceStats({ start_date: '2024-01-01' })
      const sp = mockGet.mock.calls[0][1].searchParams as URLSearchParams
      expect(sp.get('start_date')).toBe('2024-01-01')
    })

    it('sets end_date param when provided', async () => {
      mockJson.mockResolvedValue({ items: [] })
      await paymentsApi.getFinanceStats({ end_date: '2024-12-31' })
      const sp = mockGet.mock.calls[0][1].searchParams as URLSearchParams
      expect(sp.get('end_date')).toBe('2024-12-31')
    })

    it('does not set contract_id when undefined', async () => {
      mockJson.mockResolvedValue({ items: [] })
      await paymentsApi.getFinanceStats({})
      const sp = mockGet.mock.calls[0][1].searchParams as URLSearchParams
      expect(sp.has('contract_id')).toBe(false)
    })

    it('does not set start_date when undefined', async () => {
      mockJson.mockResolvedValue({ items: [] })
      await paymentsApi.getFinanceStats({})
      const sp = mockGet.mock.calls[0][1].searchParams as URLSearchParams
      expect(sp.has('start_date')).toBe(false)
    })

    it('does not set end_date when undefined', async () => {
      mockJson.mockResolvedValue({ items: [] })
      await paymentsApi.getFinanceStats({})
      const sp = mockGet.mock.calls[0][1].searchParams as URLSearchParams
      expect(sp.has('end_date')).toBe(false)
    })
  })
})
