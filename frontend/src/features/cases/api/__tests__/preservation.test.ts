const { mockPost, mockJson, mockBlob } = vi.hoisted(() => {
  const mockJson = vi.fn().mockResolvedValue({})
  const mockBlob = vi.fn().mockResolvedValue(new Blob())
  const mockPost = vi.fn().mockReturnValue({ json: mockJson, blob: mockBlob })
  return { mockPost, mockJson, mockBlob }
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
vi.stubGlobal('document', {
  ...document,
  createElement: vi.fn(() => ({
    href: '',
    download: '',
    click: mockClick,
  })),
  body: {
    ...document.body,
    appendChild: vi.fn(),
    removeChild: vi.fn(),
  },
})

import { preservationApi } from '../preservation'

describe('cases/api/preservationApi', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('downloadApplication posts to correct endpoint', async () => {
    await preservationApi.downloadApplication(1, '测试案件')
    expect(mockPost).toHaveBeenCalledWith('cases/1/preservation/application/download', { json: {} })
  })

  it('downloadDelayDelivery posts to correct endpoint', async () => {
    await preservationApi.downloadDelayDelivery(1, '测试案件')
    expect(mockPost).toHaveBeenCalledWith('cases/1/preservation/delay-delivery/download', { json: {} })
  })

  it('downloadPackage posts to correct endpoint', async () => {
    await preservationApi.downloadPackage(1, '测试案件')
    expect(mockPost).toHaveBeenCalledWith('cases/1/preservation/package/download', { json: {} })
  })
})
