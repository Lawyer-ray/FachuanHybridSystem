const { mockPost, mockJson } = vi.hoisted(() => {
  const mockJson = vi.fn().mockResolvedValue(new Blob())
  const mockBlob = vi.fn().mockResolvedValue(new Blob())
  const mockPost = vi.fn().mockReturnValue({ json: mockJson, blob: mockBlob })
  return { mockPost, mockJson }
})

vi.mock('@/lib/api', () => ({
  createFeatureApiClient: vi.fn(() => ({
    post: mockPost,
  })),
}))

vi.stubGlobal('URL', {
  createObjectURL: vi.fn(() => 'blob:url'),
  revokeObjectURL: vi.fn(),
})

const mockClick = vi.fn()
const mockAppendChild = vi.fn()
const mockRemoveChild = vi.fn()

vi.stubGlobal('document', {
  ...document,
  createElement: vi.fn(() => ({
    href: '',
    download: '',
    click: mockClick,
  })),
  body: {
    ...document.body,
    appendChild: mockAppendChild,
    removeChild: mockRemoveChild,
  },
})

import { authorizationApi } from '../authorization'

describe('cases/api/authorization', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('downloadPackage posts to correct endpoint', async () => {
    await authorizationApi.downloadPackage(1, '测试案件')
    expect(mockPost).toHaveBeenCalledWith('cases/1/authorization/package/download', { json: {} })
  })

  it('downloadLetter posts to correct endpoint', async () => {
    await authorizationApi.downloadLetter(1, '测试案件')
    expect(mockPost).toHaveBeenCalledWith('cases/1/authorization/letter/download', { json: {} })
  })

  it('downloadLegalRepCertificate posts to correct endpoint', async () => {
    await authorizationApi.downloadLegalRepCertificate(1, 10, '张三')
    expect(mockPost).toHaveBeenCalledWith('cases/1/authorization/legal-rep-certificate/10/download', { json: {} })
  })

  it('downloadCombinedPOA posts to correct endpoint', async () => {
    await authorizationApi.downloadCombinedPOA(1, '测试案件', [1, 2])
    expect(mockPost).toHaveBeenCalledWith('cases/1/authorization/power-of-attorney/combined/download', { json: { client_ids: [1, 2] } })
  })
})
