const { mockGet, mockPost, mockDelete, mockJson } = vi.hoisted(() => {
  const mockJson = vi.fn().mockResolvedValue([])
  const mockGet = vi.fn().mockReturnValue({ json: mockJson, blob: vi.fn().mockResolvedValue(new Blob()) })
  const mockPost = vi.fn().mockReturnValue({ json: mockJson })
  const mockDelete = vi.fn()
  return { mockGet, mockPost, mockDelete, mockJson }
})

vi.mock('@/lib/api', () => ({
  api: {
    get: mockGet,
    post: mockPost,
    delete: mockDelete,
  },
  createFeatureApiClient: vi.fn(() => ({
    get: mockGet,
    post: mockPost,
    delete: mockDelete,
  })),
}))

vi.mock('@/lib/download', () => ({
  downloadFromResponse: vi.fn().mockResolvedValue(undefined),
}))

import { oaApi } from '../oa'
import { archiveApi } from '../archive'
import { invoicesApi } from '../invoices'

describe('contracts/api/oa', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockJson.mockResolvedValue([])
  })

  it('fetchConfigs calls correct endpoint', async () => {
    await oaApi.fetchConfigs()
    expect(mockGet).toHaveBeenCalledWith('oa-filing/configs')
  })

  it('execute posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    await oaApi.execute('site1', 5)
    expect(mockPost).toHaveBeenCalledWith('oa-filing/execute', { json: { site_name: 'site1', contract_id: 5, case_id: null } })
  })

  it('execute passes caseId when provided', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    await oaApi.execute('site1', 5, 10)
    expect(mockPost).toHaveBeenCalledWith('oa-filing/execute', { json: { site_name: 'site1', contract_id: 5, case_id: 10 } })
  })

  it('getSession calls correct endpoint', async () => {
    await oaApi.getSession(42)
    expect(mockGet).toHaveBeenCalledWith('oa-filing/session/42')
  })
})

describe('contracts/api/archive', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockJson.mockResolvedValue([])
  })

  it('getChecklist calls correct endpoint', async () => {
    await archiveApi.getChecklist(1)
    expect(mockGet).toHaveBeenCalledWith('1/archive/checklist')
  })

  it('generateFolder posts to correct endpoint', async () => {
    await archiveApi.generateFolder(1)
    expect(mockPost).toHaveBeenCalledWith('1/archive/generate-folder')
  })

  it('learnRules posts to correct endpoint', async () => {
    await archiveApi.learnRules()
    expect(mockPost).toHaveBeenCalledWith('archive/learn-rules')
  })

  it('syncCaseMaterials posts to correct endpoint', async () => {
    await archiveApi.syncCaseMaterials(1)
    expect(mockPost).toHaveBeenCalledWith('1/archive/sync-case-materials')
  })

  it('scaleToA4 posts to correct endpoint', async () => {
    await archiveApi.scaleToA4(1)
    expect(mockPost).toHaveBeenCalledWith('1/archive/scale-to-a4')
  })

  it('toggleCompact posts to correct endpoint', async () => {
    await archiveApi.toggleCompact(1)
    expect(mockPost).toHaveBeenCalledWith('1/archive/toggle-compact')
  })

  it('confirm posts to correct endpoint', async () => {
    await archiveApi.confirm(1)
    expect(mockPost).toHaveBeenCalledWith('1/archive/confirm')
  })

  it('clearAllMaterials posts to correct endpoint', async () => {
    await archiveApi.clearAllMaterials(1)
    expect(mockPost).toHaveBeenCalledWith('1/archive/clear-all')
  })

  it('deleteMaterial calls delete on correct endpoint', async () => {
    await archiveApi.deleteMaterial(1, 5)
    expect(mockDelete).toHaveBeenCalledWith('1/archive/materials/5')
  })

  it('moveMaterial posts to correct endpoint', async () => {
    await archiveApi.moveMaterial(1, 5, 'code-1')
    expect(mockPost).toHaveBeenCalledWith('1/archive/materials/5/move', { json: { target_code: 'code-1' } })
  })

  it('reorderMaterials posts to correct endpoint', async () => {
    await archiveApi.reorderMaterials(1, { 'code-1': [3, 1, 2] })
    expect(mockPost).toHaveBeenCalledWith('1/archive/reorder', { json: { orders: { 'code-1': [3, 1, 2] } } })
  })

  it('resetAndResync posts to correct endpoint', async () => {
    await archiveApi.resetAndResync(1)
    expect(mockPost).toHaveBeenCalledWith('1/archive/reset-and-resync')
  })

  it('uploadItem posts file with FormData', async () => {
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    await archiveApi.uploadItem(1, file, '起诉状')
    expect(mockPost).toHaveBeenCalledWith('1/archive/upload', { body: expect.any(FormData) })
  })

  it('downloadItem calls correct endpoint', async () => {
    const { downloadFromResponse } = await import('@/lib/download')
    await archiveApi.downloadItem(1, 'item-code-1')
    expect(mockGet).toHaveBeenCalledWith('1/archive/download-item/item-code-1')
    expect(downloadFromResponse).toHaveBeenCalled()
  })

  it('previewItem opens blob URL in new window', async () => {
    const createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:http://test')
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(null)
    mockGet.mockReturnValueOnce({ blob: vi.fn().mockResolvedValue(new Blob(['test'])) })

    await archiveApi.previewItem(1, 'item-code-1')
    expect(mockGet).toHaveBeenCalledWith('1/archive/download-item/item-code-1?preview=1')
    expect(createObjectURLSpy).toHaveBeenCalled()
    expect(openSpy).toHaveBeenCalledWith('blob:http://test', '_blank')

    createObjectURLSpy.mockRestore()
    openSpy.mockRestore()
  })

  it('previewSingleMaterial opens blob URL in new window', async () => {
    const createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:http://test')
    const openSpy = vi.spyOn(window, 'open').mockReturnValue(null)
    mockGet.mockReturnValueOnce({ blob: vi.fn().mockResolvedValue(new Blob(['test'])) })

    await archiveApi.previewSingleMaterial(1, 5)
    expect(mockGet).toHaveBeenCalledWith('1/archive/materials/5/preview')
    expect(createObjectURLSpy).toHaveBeenCalled()
    expect(openSpy).toHaveBeenCalledWith('blob:http://test', '_blank')

    createObjectURLSpy.mockRestore()
    openSpy.mockRestore()
  })

  it('previewMaterial calls correct endpoint', async () => {
    mockGet.mockReturnValueOnce(new Response())
    await archiveApi.previewMaterial(1, 5)
    expect(mockGet).toHaveBeenCalledWith('1/archive/materials/5/preview')
  })

  it('getChecklist with string contractId', async () => {
    await archiveApi.getChecklist('abc-123')
    expect(mockGet).toHaveBeenCalledWith('abc-123/archive/checklist')
  })

  it('generateFolder with string contractId', async () => {
    await archiveApi.generateFolder('abc-123')
    expect(mockPost).toHaveBeenCalledWith('abc-123/archive/generate-folder')
  })
})

describe('contracts/api/invoices', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockJson.mockResolvedValue([])
  })

  it('list calls correct endpoint', async () => {
    await invoicesApi.list(1)
    expect(mockGet).toHaveBeenCalled()
  })

  it('create posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    await invoicesApi.create(1, { amount: 1000, invoice_number: 'INV-001', issued_at: '2025-01-01' })
    expect(mockPost).toHaveBeenCalled()
  })

  it('delete calls correct endpoint', async () => {
    await invoicesApi.delete(1, 5)
    expect(mockDelete).toHaveBeenCalledWith('1/invoices/5')
  })

  it('listClientPaymentRecords calls correct endpoint', async () => {
    await invoicesApi.listClientPaymentRecords(1)
    expect(mockGet).toHaveBeenCalledWith('1/client-payment-records')
  })

  it('createClientPaymentRecord posts FormData', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    const formData = new FormData()
    formData.append('amount', '500')
    await invoicesApi.createClientPaymentRecord(1, formData)
    expect(mockPost).toHaveBeenCalledWith('1/client-payment-records', { body: formData })
  })

  it('deleteClientPaymentRecord calls correct endpoint', async () => {
    await invoicesApi.deleteClientPaymentRecord(1, 3)
    expect(mockDelete).toHaveBeenCalledWith('1/client-payment-records/3')
  })

  it('list with string contractId', async () => {
    await invoicesApi.list('abc-123')
    expect(mockGet).toHaveBeenCalled()
  })

  it('create with optional fields', async () => {
    mockJson.mockResolvedValue({ id: 2 })
    await invoicesApi.create(1, { amount: 500 })
    expect(mockPost).toHaveBeenCalled()
  })
})
