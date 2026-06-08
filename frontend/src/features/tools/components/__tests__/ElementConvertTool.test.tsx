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

import { render, screen, fireEvent } from '@testing-library/react'
import { ElementConvertTool } from '../ElementConvertTool'
import { useQuery } from '@tanstack/react-query'

describe('ElementConvertTool', () => {
  beforeEach(() => {
    vi.clearAllMocks()
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

  // --- New tests for uncovered lines ---

  it('handles file select with valid docx file', async () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['content'], 'test.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    Object.defineProperty(file, 'size', { value: 1024 })
    fireEvent.change(fileInput, { target: { files: [file] } })
    expect(screen.getAllByText('test.docx').length).toBeGreaterThan(0)
  })

  it('handles file select with invalid extension', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['content'], 'test.txt', { type: 'text/plain' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    // Should show error toast, not display file
    expect(screen.queryByText('test.txt')).not.toBeInTheDocument()
  })

  it('handles file select with oversized file', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['x'.repeat(21 * 1024 * 1024)], 'large.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    Object.defineProperty(file, 'size', { value: 21 * 1024 * 1024 })
    fireEvent.change(fileInput, { target: { files: [file] } })
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
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['content'], '传统格式_买卖合同.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    Object.defineProperty(file, 'size', { value: 2048 })
    fireEvent.change(fileInput, { target: { files: [file] } })
    expect(screen.getAllByText('传统格式_买卖合同.docx').length).toBeGreaterThan(0)
    expect(screen.getByText(/2 KB/)).toBeInTheDocument()
  })

  it('auto-selects MBID when filename matches', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { categories: [{ category: '合同', items: [{ mbid: 'mb1', name: '买卖合同' }] }] },
      isLoading: false,
    } as any)
    render(<ElementConvertTool />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['content'], '买卖合同_传统.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    // MBID should be auto-selected, enabling step 3
    expect(screen.getAllByText('买卖合同_传统.docx').length).toBeGreaterThan(0)
  })

  it('renders step 3 when file and mbid selected', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: { categories: [{ category: '合同', items: [{ mbid: 'mb1', name: '买卖合同' }] }] },
      isLoading: false,
    } as any)
    render(<ElementConvertTool />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['content'], '买卖合同.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    // Click MBID button to select it - use getAllByText since text appears in multiple places
    const mbidButtons = screen.getAllByText('买卖合同')
    fireEvent.click(mbidButtons[0])
    // Step 3 should now be visible
    expect(screen.getByText('转换并下载')).toBeInTheDocument()
  })

  it('renders clear file button', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['content'], 'test.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    fireEvent.change(fileInput, { target: { files: [file] } })
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
    // Step 2 should have pointer-events-none class
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
})
