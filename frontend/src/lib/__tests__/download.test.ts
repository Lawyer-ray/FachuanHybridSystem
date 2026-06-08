const mockClick = vi.fn()
const mockCreateObjectURL = vi.fn().mockReturnValue('blob:mock-url')
const mockRevokeObjectURL = vi.fn()

let createdAnchor: Record<string, unknown> | null = null

beforeEach(() => {
  vi.clearAllMocks()
  createdAnchor = null

  vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
    if (tag === 'a') {
      createdAnchor = { href: '', download: '', click: mockClick }
      return createdAnchor as unknown as HTMLAnchorElement
    }
    return document.createElement(tag)
  })

  vi.spyOn(document.body, 'appendChild').mockImplementation(() => null as unknown as Node)
  vi.spyOn(document.body, 'removeChild').mockImplementation(() => null as unknown as Node)

  vi.stubGlobal('URL', {
    createObjectURL: mockCreateObjectURL,
    revokeObjectURL: mockRevokeObjectURL,
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

const { downloadBlob, downloadFromResponse } = await import('../download')

describe('downloadBlob', () => {
  it('creates a download link and clicks it', () => {
    const blob = new Blob(['test'])
    downloadBlob(blob, 'test.txt')
    expect(mockCreateObjectURL).toHaveBeenCalledWith(blob)
    expect(mockClick).toHaveBeenCalled()
  })

  it('sets the download filename', () => {
    const blob = new Blob(['test'])
    downloadBlob(blob, 'report.pdf')
    expect(createdAnchor!.download).toBe('report.pdf')
  })

  it('revokes the object URL after download', () => {
    const blob = new Blob(['test'])
    downloadBlob(blob, 'test.txt')
    expect(mockRevokeObjectURL).toHaveBeenCalledWith('blob:mock-url')
  })

  it('appends and removes anchor from body', () => {
    const appendSpy = document.body.appendChild as unknown as ReturnType<typeof vi.spyOn>
    const removeSpy = document.body.removeChild as unknown as ReturnType<typeof vi.spyOn>
    downloadBlob(new Blob(['x']), 'f.txt')
    expect(appendSpy).toHaveBeenCalled()
    expect(removeSpy).toHaveBeenCalled()
  })
})

describe('downloadFromResponse', () => {
  function createMockResponse(headers: Record<string, string> = {}): Response {
    const headerMap = new Headers(headers)
    return {
      blob: vi.fn().mockResolvedValue(new Blob(['data'])),
      headers: headerMap,
    } as unknown as Response
  }

  it('uses fallback filename when no Content-Disposition', async () => {
    const response = createMockResponse()
    await downloadFromResponse(response, 'fallback.pdf')
    expect(createdAnchor!.download).toBe('fallback.pdf')
  })

  it('extracts UTF-8 filename from Content-Disposition', async () => {
    const response = createMockResponse({
      'Content-Disposition': "attachment; filename*=UTF-8''%E6%B5%8B%E8%AF%95.pdf",
    })
    await downloadFromResponse(response)
    expect(createdAnchor!.download).toBe('测试.pdf')
  })

  it('extracts plain filename from Content-Disposition', async () => {
    const response = createMockResponse({
      'Content-Disposition': 'attachment; filename="report.pdf"',
    })
    await downloadFromResponse(response)
    expect(createdAnchor!.download).toBe('report.pdf')
  })

  it('uses default fallback when no disposition and no fallback param', async () => {
    const response = createMockResponse()
    await downloadFromResponse(response)
    expect(createdAnchor!.download).toBe('download')
  })
})
