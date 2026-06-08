const { mockGet, mockPost, mockDelete, mockJson } = vi.hoisted(() => {
  const mockJson = vi.fn().mockResolvedValue([])
  const mockGet = vi.fn().mockReturnValue({ json: mockJson, blob: vi.fn().mockResolvedValue(new Blob()) })
  const mockPost = vi.fn().mockReturnValue({ json: mockJson, blob: vi.fn().mockResolvedValue(new Blob()) })
  const mockDelete = vi.fn().mockReturnValue({ json: mockJson })
  return { mockGet, mockPost, mockDelete, mockJson }
})

vi.mock('@/lib/api', () => ({
  createFeatureApiClient: vi.fn(() => ({
    get: mockGet,
    post: mockPost,
    delete: mockDelete,
  })),
}))

import { materialsApi } from '../materials'

describe('cases/api/materialsApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockJson.mockResolvedValue([])
  })

  it('listCandidates calls correct endpoint', async () => {
    await materialsApi.listCandidates(1)
    expect(mockGet).toHaveBeenCalledWith('1/materials/bind-candidates')
  })

  it('bind posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ saved_count: 2 })
    await materialsApi.bind(1, [{ type_id: 1, attachment_id: 10 }])
    expect(mockPost).toHaveBeenCalledWith('1/materials/bind', { json: { items: [{ type_id: 1, attachment_id: 10 }] } })
  })

  it('upload posts with FormData', async () => {
    const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })
    mockJson.mockResolvedValue({ files: [] })
    await materialsApi.upload(1, [file])
    expect(mockPost).toHaveBeenCalledWith('1/materials/upload', expect.objectContaining({
      body: expect.any(FormData),
    }))
  })

  it('replace posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ success: true })
    await materialsApi.replace(1, 5, 10)
    expect(mockPost).toHaveBeenCalledWith('1/materials/5/replace', { json: { new_attachment_id: 10 } })
  })

  it('renameGroup posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ success: true })
    await materialsApi.renameGroup(1, 5, '新名称', true)
    expect(mockPost).toHaveBeenCalledWith('1/materials/group-rename', {
      json: { type_id: 5, new_type_name: '新名称', update_global: true },
    })
  })

  it('delete calls correct endpoint', async () => {
    mockJson.mockResolvedValue({ success: true })
    await materialsApi.delete(1, 5)
    expect(mockDelete).toHaveBeenCalledWith('1/materials/5')
  })

  it('deleteAll calls correct endpoint with category', async () => {
    mockJson.mockResolvedValue({ deleted: 3 })
    await materialsApi.deleteAll(1, 'party')
    expect(mockDelete).toHaveBeenCalledWith('1/materials', { json: { category: 'party' } })
  })

  it('saveGroupOrder posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ ok: true })
    await materialsApi.saveGroupOrder(1, 'party', [3, 1, 2])
    expect(mockPost).toHaveBeenCalledWith('1/materials/group-order', {
      json: { category: 'party', ordered_type_ids: [3, 1, 2], side: undefined, supervising_authority_id: undefined },
    })
  })

  it('getTemplateBindings calls correct endpoint', async () => {
    mockJson.mockResolvedValue({ categories: [] })
    await materialsApi.getTemplateBindings(1)
    expect(mockGet).toHaveBeenCalledWith('1/template-bindings')
  })

  it('bindTemplate posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    await materialsApi.bindTemplate(1, 5)
    expect(mockPost).toHaveBeenCalledWith('1/template-bindings', { json: { template_id: 5 } })
  })

  it('unbindTemplate deletes correct endpoint', async () => {
    mockJson.mockResolvedValue({ success: true })
    await materialsApi.unbindTemplate(1, 5)
    expect(mockDelete).toHaveBeenCalledWith('1/template-bindings/5')
  })

  it('getAvailableTemplates calls correct endpoint', async () => {
    mockJson.mockResolvedValue([])
    await materialsApi.getAvailableTemplates(1)
    expect(mockGet).toHaveBeenCalledWith('1/available-templates')
  })

  it('generateTemplate posts and returns blob', async () => {
    await materialsApi.generateTemplate(1, { template_id: 5, party_id: 10 })
    expect(mockPost).toHaveBeenCalledWith('1/generate-template', { json: { template_id: 5, party_id: 10 } })
  })

  it('unifiedGenerate posts and returns blob', async () => {
    await materialsApi.unifiedGenerate(1, { template_id: 5 })
    expect(mockPost).toHaveBeenCalledWith('1/unified-generate', { json: { template_id: 5 } })
  })

  it('getFolderBinding calls correct endpoint', async () => {
    mockJson.mockResolvedValue({ folder_path: '/docs' })
    await materialsApi.getFolderBinding(1)
    expect(mockGet).toHaveBeenCalledWith('1/folder-binding')
  })

  it('createFolderBinding posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    await materialsApi.createFolderBinding(1, { folder_path: '/docs' })
    expect(mockPost).toHaveBeenCalledWith('1/folder-binding', { json: { folder_path: '/docs' } })
  })

  it('deleteFolderBinding deletes correct endpoint', async () => {
    await materialsApi.deleteFolderBinding(1)
    expect(mockDelete).toHaveBeenCalledWith('1/folder-binding')
  })

  it('browseFolders calls correct endpoint', async () => {
    mockJson.mockResolvedValue({ folders: [] })
    await materialsApi.browseFolders('/docs', 'local', 1)
    expect(mockGet).toHaveBeenCalledWith('folder-browse', expect.objectContaining({
      searchParams: expect.any(URLSearchParams),
    }))
  })

  it('listCloudStorageAccounts calls correct endpoint', async () => {
    mockJson.mockResolvedValue([])
    await materialsApi.listCloudStorageAccounts()
    expect(mockGet).toHaveBeenCalledWith('cloud-storage-accounts')
  })

  it('startFolderScan posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ session_id: 'abc' })
    await materialsApi.startFolderScan(1, { force: true })
    expect(mockPost).toHaveBeenCalledWith('1/folder-scan', { json: { force: true } })
  })

  it('getScanStatus calls correct endpoint', async () => {
    mockJson.mockResolvedValue({ status: 'done' })
    await materialsApi.getScanStatus(1, 'session-abc')
    expect(mockGet).toHaveBeenCalledWith('1/folder-scan/session-abc')
  })

  it('stageScanResults posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ staged_count: 5 })
    const items = [{ file_path: '/test.pdf', type_id: 1 }]
    await materialsApi.stageScanResults(1, 'session-abc', items as any)
    expect(mockPost).toHaveBeenCalledWith('1/folder-scan/session-abc/stage', { json: { items } })
  })
})
