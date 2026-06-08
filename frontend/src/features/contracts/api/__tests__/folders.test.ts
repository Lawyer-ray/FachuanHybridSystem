const { mockGet, mockPost, mockDelete, mockJson } = vi.hoisted(() => {
  const mockJson = vi.fn().mockResolvedValue(null)
  const mockGet = vi.fn().mockReturnValue({ json: mockJson })
  const mockPost = vi.fn().mockReturnValue({ json: mockJson })
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

import { foldersApi } from '../folders'

describe('contracts/api/folders', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockJson.mockResolvedValue(null)
  })

  it('getBinding calls correct endpoint', async () => {
    await foldersApi.getBinding(1)
    expect(mockGet).toHaveBeenCalledWith('1/folder-binding')
  })

  it('createBinding posts to correct endpoint', async () => {
    mockJson.mockResolvedValue({ id: 1 })
    await foldersApi.createBinding(1, { folder_path: '/path/to/folder' })
    expect(mockPost).toHaveBeenCalledWith('1/folder-binding', { json: { folder_path: '/path/to/folder' } })
  })

  it('deleteBinding calls delete on correct endpoint', async () => {
    await foldersApi.deleteBinding(1)
    expect(mockDelete).toHaveBeenCalledWith('1/folder-binding')
  })

  it('browse calls correct endpoint', async () => {
    await foldersApi.browse('/path')
    expect(mockGet).toHaveBeenCalledWith('folder-browse', { searchParams: expect.any(URLSearchParams) })
  })

  it('startScan posts to correct endpoint', async () => {
    await foldersApi.startScan(1)
    expect(mockPost).toHaveBeenCalledWith('1/folder-scan', { json: { rescan: false, scan_subfolder: '' } })
  })

  it('startScan with rescan flag', async () => {
    await foldersApi.startScan(1, true)
    expect(mockPost).toHaveBeenCalledWith('1/folder-scan', { json: { rescan: true, scan_subfolder: '' } })
  })

  it('listScanSubfolders calls correct endpoint', async () => {
    await foldersApi.listScanSubfolders(1)
    expect(mockGet).toHaveBeenCalledWith('1/folder-scan/subfolders')
  })

  it('getScanStatus calls correct endpoint', async () => {
    await foldersApi.getScanStatus(1, 'sess-1')
    expect(mockGet).toHaveBeenCalledWith('1/folder-scan/sess-1')
  })

  it('confirmScan posts to correct endpoint', async () => {
    await foldersApi.confirmScan(1, 'sess-1', [{ file_path: '/path', category: 'contract' }])
    expect(mockPost).toHaveBeenCalledWith('1/folder-scan/sess-1/confirm', { json: { items: [{ file_path: '/path', category: 'contract' }] } })
  })

  it('listCloudStorageAccounts calls correct endpoint', async () => {
    await foldersApi.listCloudStorageAccounts()
    expect(mockGet).toHaveBeenCalledWith('cloud-storage-accounts')
  })
})
