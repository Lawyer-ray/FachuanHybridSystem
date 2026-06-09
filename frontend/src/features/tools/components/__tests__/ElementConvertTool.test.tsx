/**
 * ElementConvertTool Component Tests
 * 测试要素式转换工具组件
 */

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn() },
}))

vi.mock('@tanstack/react-query', () => ({
  useQuery: vi.fn(),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, className }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} className={className as string}>{children}</button>
  ),
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, className }: Record<string, unknown>) => <div className={className as string}>{children}</div>,
  CardContent: ({ children, className }: Record<string, unknown>) => <div className={className as string}>{children}</div>,
}))

vi.mock('ky', () => ({
  HTTPError: class HTTPError extends Error {},
}))

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ElementConvertTool } from '../ElementConvertTool'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { toast } from 'sonner'
import { HTTPError } from 'ky'

const mockCategories = [
  { category: '合同纠纷', items: [{ mbid: 'mb1', name: '买卖合同' }, { mbid: 'mb2', name: '借款合同' }] },
]

function mockUseQueryWithData() {
  vi.mocked(useQuery).mockReturnValue({
    data: { categories: mockCategories },
    isLoading: false,
  } as any)
}

function selectFile(name: string, size = 1024) {
  const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
  const file = new File(['content'], name, { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
  Object.defineProperty(file, 'size', { value: size })
  fireEvent.change(fileInput, { target: { files: [file] } })
  return file
}

function selectMbid(label: string) {
  const buttons = screen.getAllByText(label)
  fireEvent.click(buttons[0])
}

describe('ElementConvertTool', () => {
  let originalCreateElement: typeof document.createElement
  let urlSpy: { createObjectURL: ReturnType<typeof vi.fn>; revokeObjectURL: ReturnType<typeof vi.fn> }

  beforeEach(() => {
    vi.clearAllMocks()
    originalCreateElement = document.createElement.bind(document)
    urlSpy = { createObjectURL: vi.fn(() => 'blob:url'), revokeObjectURL: vi.fn() }
    vi.stubGlobal('URL', { ...URL, ...urlSpy })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    // Restore createElement if it was overridden via direct assignment
    document.createElement = originalCreateElement
  })

  it('renders page title', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    expect(screen.getByText('要素式转换')).toBeInTheDocument()
  })

  it('renders step indicators', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    expect(screen.getByText('上传文书')).toBeInTheDocument()
    expect(screen.getByText('选择格式')).toBeInTheDocument()
    expect(screen.getByText('转换下载')).toBeInTheDocument()
  })

  it('renders upload area when no file selected', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    expect(screen.getByText(/点击选择或拖拽文件到此处/)).toBeInTheDocument()
    expect(screen.getByText(/支持 .docx、.doc、.pdf 格式/)).toBeInTheDocument()
  })

  it('shows loading state for format list', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: true } as any)
    render(<ElementConvertTool />)
    expect(screen.getByText('加载格式列表...')).toBeInTheDocument()
  })

  it('renders category list when data is loaded', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: {
        categories: [
          { category: '合同纠纷', items: [{ mbid: 'mb1', name: '买卖合同' }, { mbid: 'mb2', name: '借款合同' }] },
        ],
      },
      isLoading: false,
    } as any)
    render(<ElementConvertTool />)
    expect(screen.getByText('合同纠纷')).toBeInTheDocument()
    expect(screen.getByText('买卖合同')).toBeInTheDocument()
    expect(screen.getByText('借款合同')).toBeInTheDocument()
  })

  it('renders description text', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    expect(screen.getByText(/上传传统格式文书，系统自动识别并转换为要素式标准格式/)).toBeInTheDocument()
  })

  // --- File selection tests ---

  it('handles file select with valid docx file', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    selectFile('test.docx')
    expect(screen.getAllByText('test.docx').length).toBeGreaterThan(0)
  })

  it('handles file select with invalid extension', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['content'], 'test.txt', { type: 'text/plain' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    expect(screen.queryByText('test.txt')).not.toBeInTheDocument()
  })

  it('handles file select with oversized file', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    selectFile('large.docx', 21 * 1024 * 1024)
    expect(screen.queryByText('large.docx')).not.toBeInTheDocument()
  })

  it('handles drag and drop with valid file', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    const dropZone = screen.getByText(/点击选择或拖拽文件到此处/).closest('div')!
    const file = new File(['content'], 'dropped.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    fireEvent.dragOver(dropZone)
    fireEvent.drop(dropZone, { dataTransfer: { files: [file] } })
    expect(screen.getAllByText('dropped.docx').length).toBeGreaterThan(0)
  })

  it('handles drag and drop with invalid extension', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    const dropZone = screen.getByText(/点击选择或拖拽文件到此处/).closest('div')!
    const file = new File(['content'], 'dropped.txt', { type: 'text/plain' })
    fireEvent.drop(dropZone, { dataTransfer: { files: [file] } })
    expect(screen.queryByText('dropped.txt')).not.toBeInTheDocument()
  })

  it('handles drag and drop with no file', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    const dropZone = screen.getByText(/点击选择或拖拽文件到此处/).closest('div')!
    fireEvent.drop(dropZone, { dataTransfer: { files: [] } })
  })

  it('handles file select with no file', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(fileInput, { target: { files: [] } })
  })

  it('renders file details when file is selected', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { categories: [{ category: '合同', items: [{ mbid: 'mb1', name: '买卖合同' }] }] },
      isLoading: false,
    } as any)
    render(<ElementConvertTool />)
    selectFile('传统格式_买卖合同.docx', 2048)
    expect(screen.getAllByText('传统格式_买卖合同.docx').length).toBeGreaterThan(0)
    expect(screen.getByText(/2 KB/)).toBeInTheDocument()
  })

  it('auto-selects MBID when filename matches', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { categories: [{ category: '合同', items: [{ mbid: 'mb1', name: '买卖合同' }] }] },
      isLoading: false,
    } as any)
    render(<ElementConvertTool />)
    selectFile('买卖合同_传统.docx')
    expect(screen.getAllByText('买卖合同_传统.docx').length).toBeGreaterThan(0)
  })

  it('renders step 3 when file and mbid selected', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { categories: [{ category: '合同', items: [{ mbid: 'mb1', name: '买卖合同' }] }] },
      isLoading: false,
    } as any)
    render(<ElementConvertTool />)
    selectFile('买卖合同.docx')
    const mbidButtons = screen.getAllByText('买卖合同')
    fireEvent.click(mbidButtons[0])
    expect(screen.getByText('转换并下载')).toBeInTheDocument()
  })

  it('renders clear file button', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    selectFile('test.docx')
    expect(screen.getAllByText('test.docx').length).toBeGreaterThan(0)
  })

  it('renders with pdf file type', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    expect(screen.getAllByText('test.pdf').length).toBeGreaterThan(0)
  })

  it('renders step 2 disabled when no file selected', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { categories: [{ category: '合同', items: [{ mbid: 'mb1', name: '买卖合同' }] }] },
      isLoading: false,
    } as any)
    render(<ElementConvertTool />)
    expect(screen.getByText('买卖合同')).toBeInTheDocument()
  })

  it('handles doc file type', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['content'], 'test.doc', { type: 'application/msword' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    expect(screen.getAllByText('test.doc').length).toBeGreaterThan(0)
  })

  // --- Conversion tests ---

  it('triggers download on successful convert', async () => {
    const mockBlob = new Blob(['converted'])
    const mockClick = vi.fn()
    // Override createElement only for 'a' tags, using the real impl for others
    document.createElement = ((tag: string) => {
      if (tag === 'a') {
        return { href: '', download: '', click: mockClick } as unknown as HTMLAnchorElement
      }
      return originalCreateElement(tag)
    }) as typeof document.createElement

    vi.mocked(api.post).mockResolvedValue({ blob: () => Promise.resolve(mockBlob) } as any)
    mockUseQueryWithData()
    render(<ElementConvertTool />)

    selectFile('传统格式_买卖合同.docx')
    await waitFor(() => expect(screen.getByText('转换并下载')).toBeInTheDocument())
    fireEvent.click(screen.getByText('转换并下载'))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('doc-convert/convert', expect.objectContaining({ timeout: 120_000 }))
      expect(urlSpy.createObjectURL).toHaveBeenCalledWith(mockBlob)
      expect(mockClick).toHaveBeenCalled()
      expect(toast.success).toHaveBeenCalledWith('转换完成，文件已下载')
    })
  })

  it('renames 传统 to 要素式 in downloaded filename', async () => {
    const mockBlob = new Blob(['x'])
    const mockClick = vi.fn()
    let downloadName = ''
    document.createElement = ((tag: string) => {
      if (tag === 'a') {
        return new Proxy({} as HTMLAnchorElement, {
          set(_target, prop, value) {
            if (prop === 'download') downloadName = value as string
            return true
          },
          get(_target, prop) {
            if (prop === 'click') return mockClick
            return undefined
          },
        })
      }
      return originalCreateElement(tag)
    }) as typeof document.createElement

    vi.mocked(api.post).mockResolvedValue({ blob: () => Promise.resolve(mockBlob) } as any)
    mockUseQueryWithData()
    render(<ElementConvertTool />)

    selectFile('传统格式_买卖合同.docx')
    await waitFor(() => expect(screen.getByText('转换并下载')).toBeInTheDocument())
    fireEvent.click(screen.getByText('转换并下载'))

    await waitFor(() => {
      expect(downloadName).toBe('要素式格式_买卖合同.docx')
    })
  })

  it('prepends 要素式 when filename has no 传统', async () => {
    const mockBlob = new Blob(['x'])
    const mockClick = vi.fn()
    let downloadName = ''
    document.createElement = ((tag: string) => {
      if (tag === 'a') {
        return new Proxy({} as HTMLAnchorElement, {
          set(_target, prop, value) {
            if (prop === 'download') downloadName = value as string
            return true
          },
          get(_target, prop) {
            if (prop === 'click') return mockClick
            return undefined
          },
        })
      }
      return originalCreateElement(tag)
    }) as typeof document.createElement

    vi.mocked(api.post).mockResolvedValue({ blob: () => Promise.resolve(mockBlob) } as any)
    mockUseQueryWithData()
    render(<ElementConvertTool />)

    selectFile('买卖合同.docx')
    selectMbid('买卖合同')
    await waitFor(() => expect(screen.getByText('转换并下载')).toBeInTheDocument())
    fireEvent.click(screen.getByText('转换并下载'))

    await waitFor(() => {
      expect(downloadName).toBe('要素式买卖合同.docx')
    })
  })

  it('handles HTTPError 502 with detail', async () => {
    const mockResponse = { status: 502, json: vi.fn().mockResolvedValue({ detail: '远端服务不可用' }) }
    const err = Object.create(HTTPError.prototype, {
      response: { value: mockResponse },
    })
    vi.mocked(api.post).mockRejectedValue(err)
    mockUseQueryWithData()
    render(<ElementConvertTool />)

    selectFile('买卖合同.docx')
    selectMbid('买卖合同')
    await waitFor(() => expect(screen.getByText('转换并下载')).toBeInTheDocument())
    fireEvent.click(screen.getByText('转换并下载'))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('远端服务不可用')
    })
  })

  it('handles HTTPError 502 without detail', async () => {
    const mockResponse = { status: 502, json: vi.fn().mockResolvedValue({}) }
    const err = Object.create(HTTPError.prototype, {
      response: { value: mockResponse },
    })
    vi.mocked(api.post).mockRejectedValue(err)
    mockUseQueryWithData()
    render(<ElementConvertTool />)

    selectFile('买卖合同.docx')
    selectMbid('买卖合同')
    await waitFor(() => expect(screen.getByText('转换并下载')).toBeInTheDocument())
    fireEvent.click(screen.getByText('转换并下载'))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('远端转换服务暂时不可用，请稍后重试')
    })
  })

  it('handles HTTPError non-502 with detail', async () => {
    const mockResponse = { status: 400, json: vi.fn().mockResolvedValue({ detail: '文件格式错误' }) }
    const err = Object.create(HTTPError.prototype, {
      response: { value: mockResponse },
    })
    vi.mocked(api.post).mockRejectedValue(err)
    mockUseQueryWithData()
    render(<ElementConvertTool />)

    selectFile('买卖合同.docx')
    selectMbid('买卖合同')
    await waitFor(() => expect(screen.getByText('转换并下载')).toBeInTheDocument())
    fireEvent.click(screen.getByText('转换并下载'))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('文件格式错误')
    })
  })

  it('handles HTTPError non-502 without detail', async () => {
    const mockResponse = { status: 400, json: vi.fn().mockResolvedValue({}) }
    const err = Object.create(HTTPError.prototype, {
      response: { value: mockResponse },
    })
    vi.mocked(api.post).mockRejectedValue(err)
    mockUseQueryWithData()
    render(<ElementConvertTool />)

    selectFile('买卖合同.docx')
    selectMbid('买卖合同')
    await waitFor(() => expect(screen.getByText('转换并下载')).toBeInTheDocument())
    fireEvent.click(screen.getByText('转换并下载'))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('请求失败 (400)')
    })
  })

  it('handles HTTPError when response.json() throws (502)', async () => {
    const mockResponse = { status: 502, json: vi.fn().mockRejectedValue(new Error('parse error')) }
    const err = Object.create(HTTPError.prototype, {
      response: { value: mockResponse },
    })
    vi.mocked(api.post).mockRejectedValue(err)
    mockUseQueryWithData()
    render(<ElementConvertTool />)

    selectFile('买卖合同.docx')
    selectMbid('买卖合同')
    await waitFor(() => expect(screen.getByText('转换并下载')).toBeInTheDocument())
    fireEvent.click(screen.getByText('转换并下载'))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('远端转换服务暂时不可用，请稍后重试')
    })
  })

  it('handles HTTPError when response.json() throws (non-502)', async () => {
    const mockResponse = { status: 400, json: vi.fn().mockRejectedValue(new Error('parse error')) }
    const err = Object.create(HTTPError.prototype, {
      response: { value: mockResponse },
    })
    vi.mocked(api.post).mockRejectedValue(err)
    mockUseQueryWithData()
    render(<ElementConvertTool />)

    selectFile('买卖合同.docx')
    selectMbid('买卖合同')
    await waitFor(() => expect(screen.getByText('转换并下载')).toBeInTheDocument())
    fireEvent.click(screen.getByText('转换并下载'))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('请求失败 (400)')
    })
  })

  it('handles generic Error', async () => {
    vi.mocked(api.post).mockRejectedValue(new Error('网络超时'))
    mockUseQueryWithData()
    render(<ElementConvertTool />)

    selectFile('买卖合同.docx')
    selectMbid('买卖合同')
    await waitFor(() => expect(screen.getByText('转换并下载')).toBeInTheDocument())
    fireEvent.click(screen.getByText('转换并下载'))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('网络超时')
    })
  })

  it('handles non-Error exception', async () => {
    vi.mocked(api.post).mockRejectedValue('unknown error')
    mockUseQueryWithData()
    render(<ElementConvertTool />)

    selectFile('买卖合同.docx')
    selectMbid('买卖合同')
    await waitFor(() => expect(screen.getByText('转换并下载')).toBeInTheDocument())
    fireEvent.click(screen.getByText('转换并下载'))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('转换失败')
    })
  })

  it('shows converting state and disables button', async () => {
    let resolvePost: (v: unknown) => void
    vi.mocked(api.post).mockReturnValue(new Promise((resolve) => { resolvePost = resolve }) as any)
    mockUseQueryWithData()
    render(<ElementConvertTool />)

    selectFile('买卖合同.docx')
    selectMbid('买卖合同')
    await waitFor(() => expect(screen.getByText('转换并下载')).toBeInTheDocument())
    fireEvent.click(screen.getByText('转换并下载'))

    await waitFor(() => {
      expect(screen.getByText('转换中...')).toBeInTheDocument()
    })

    resolvePost!({ blob: () => Promise.resolve(new Blob(['x'])) })
    await waitFor(() => {
      expect(screen.getByText('转换并下载')).toBeInTheDocument()
    })
  })

  // --- Clear file button ---

  it('clears selected file and resets mbid when X is clicked', () => {
    mockUseQueryWithData()
    render(<ElementConvertTool />)

    selectFile('买卖合同.docx')
    expect(screen.getAllByText('买卖合同.docx').length).toBeGreaterThan(0)

    // Find the close button (X icon wrapper)
    const closeButtons = document.querySelectorAll('.hover\\:bg-muted')
    expect(closeButtons.length).toBeGreaterThan(0)
    fireEvent.click(closeButtons[0])

    // File should be removed, upload area should reappear
    expect(screen.queryByText('买卖合同.docx')).not.toBeInTheDocument()
    expect(screen.getByText(/点击选择或拖拽文件到此处/)).toBeInTheDocument()
  })

  // --- MBID selection ---

  it('selects MBID when clicking a format button', () => {
    mockUseQueryWithData()
    render(<ElementConvertTool />)

    selectFile('test.docx')
    selectMbid('借款合同')

    // Step 3 should show the selected MBID name in the conversion summary
    expect(screen.getByText('借款合同', { selector: '.text-foreground.font-medium' })).toBeInTheDocument()
  })

  // --- Drop handler ---

  it('prevents default on dragOver', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    const dropZone = screen.getByText(/点击选择或拖拽文件到此处/).closest('div')!
    const event = new Event('dragOver', { bubbles: true, cancelable: true })
    fireEvent(dropZone, event)
    // Should not throw
  })
})
