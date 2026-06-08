vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))

vi.mock('lucide-react', () => {
  const Icon = (p: Record<string, unknown>) => <svg data-testid="icon" {...p} />
  return {
    FileText: Icon, Loader2: Icon, CheckCircle2: Icon, Wand2: Icon,
    Image: Icon, X: Icon, ChevronDown: Icon,
  }
})

vi.mock('framer-motion', () => ({
  motion: {
    div: (p: Record<string, unknown>) => <div {...p}>{(p as Record<string, unknown>).children}</div>,
  },
  AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

vi.mock('../../api', () => ({
  clientApi: {
    parseText: vi.fn(),
    recognizeIdentityDoc: vi.fn(),
  },
}))

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { TextParser } from '../TextParser'
import { clientApi } from '../../api'

describe('TextParser', () => {
  const defaultProps = {
    onParsed: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the title button', () => {
    render(<TextParser {...defaultProps} />)
    expect(screen.getByText('智能解析')).toBeInTheDocument()
  })

  it('shows the hint text', () => {
    render(<TextParser {...defaultProps} />)
    expect(screen.getByText('粘贴文本或上传证件图片，AI 自动提取')).toBeInTheDocument()
  })

  it('expands when title is clicked', () => {
    render(<TextParser {...defaultProps} />)
    const titleButton = screen.getByText('智能解析').closest('button')!
    fireEvent.click(titleButton)
    expect(screen.getByPlaceholderText(/粘贴当事人信息文本/)).toBeInTheDocument()
  })

  it('shows parse button when expanded', () => {
    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)
    expect(screen.getByText('解析文本')).toBeInTheDocument()
  })

  it('shows upload image button when expanded', () => {
    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)
    expect(screen.getByText('上传图片')).toBeInTheDocument()
  })

  it('calls parseText API when parse button is clicked with text', async () => {
    vi.mocked(clientApi.parseText).mockResolvedValue({
      success: true,
      client: { name: 'Wang', id_number: '000000000000000100' },
    })

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)

    const textarea = screen.getByPlaceholderText(/粘贴当事人信息文本/)
    fireEvent.change(textarea, { target: { value: 'some text' } })
    fireEvent.click(screen.getByText('解析文本'))

    await waitFor(() => {
      expect(clientApi.parseText).toHaveBeenCalledWith('some text')
    })
  })

  it('displays parse result and calls onParsed when confirmed', async () => {
    vi.mocked(clientApi.parseText).mockResolvedValue({
      success: true,
      client: { name: 'Wang' },
    })

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)

    const textarea = screen.getByPlaceholderText(/粘贴当事人信息文本/)
    fireEvent.change(textarea, { target: { value: 'some text' } })
    fireEvent.click(screen.getByText('解析文本'))

    await waitFor(() => {
      expect(screen.getByText('解析成功')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('确认填充'))
    expect(defaultProps.onParsed).toHaveBeenCalledWith({ name: 'Wang' })
  })

  it('shows error toast when parse fails with no data', async () => {
    vi.mocked(clientApi.parseText).mockResolvedValue({
      success: false,
      client: null,
      error: '未能解析',
    })

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)
    const textarea = screen.getByPlaceholderText(/粘贴当事人信息文本/)
    fireEvent.change(textarea, { target: { value: 'bad text' } })
    fireEvent.click(screen.getByText('解析文本'))

    const { toast } = await import('sonner')
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('未能解析')
    })
  })

  it('shows error toast when parse throws', async () => {
    vi.mocked(clientApi.parseText).mockRejectedValue(new Error('network'))

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)
    const textarea = screen.getByPlaceholderText(/粘贴当事人信息文本/)
    fireEvent.change(textarea, { target: { value: 'text' } })
    fireEvent.click(screen.getByText('解析文本'))

    const { toast } = await import('sonner')
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('解析失败，请重试')
    })
  })

  it('shows error toast when text is empty', async () => {
    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)
    // Parse button should be disabled when no text, so manually trigger parse via button
    const parseBtn = screen.getByText('解析文本')
    expect(parseBtn).toBeDisabled()
  })

  it('handles file select and calls recognizeIdentityDoc', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: true,
      extracted_data: { name: 'Wang', id_number: '12345', address: 'Beijing' },
    })

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'id.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(clientApi.recognizeIdentityDoc).toHaveBeenCalledWith(file)
      expect(screen.getByText('解析成功')).toBeInTheDocument()
    })
  })

  it('shows error when image recognition fails', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: false,
      error: '识别失败',
    })

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'id.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    const { toast } = await import('sonner')
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('识别失败')
    })
  })

  it('shows error when image recognition throws', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockRejectedValue(new Error('fail'))

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'id.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    const { toast } = await import('sonner')
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('识别失败，请检查网络')
    })
  })

  it('handles clear image', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: true,
      extracted_data: { name: 'Wang' },
    })

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'id.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('id.jpg')).toBeInTheDocument()
    })
  })

  it('handles paste with image data', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: true,
      extracted_data: { name: 'Pasted' },
    })

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)

    const textarea = screen.getByPlaceholderText(/粘贴当事人信息文本/)
    const mockFile = new File(['test'], 'pasted.png', { type: 'image/png' })
    fireEvent.paste(textarea, {
      clipboardData: {
        items: [{ type: 'image/png', getAsFile: () => mockFile }],
      },
    })

    await waitFor(() => {
      expect(clientApi.recognizeIdentityDoc).toHaveBeenCalled()
    })
  })

  it('does not trigger paste handler when no image items', () => {
    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)

    const textarea = screen.getByPlaceholderText(/粘贴当事人信息文本/)
    const pasteEvent = new Event('paste', { bubbles: true }) as unknown as React.ClipboardEvent
    Object.defineProperty(pasteEvent, 'clipboardData', {
      value: {
        items: [{ type: 'text/plain', getAsFile: () => null }],
      },
    })
    fireEvent.paste(textarea, pasteEvent)
    expect(clientApi.recognizeIdentityDoc).not.toHaveBeenCalled()
  })

  it('calls onParsed with all fields when all present', async () => {
    vi.mocked(clientApi.parseText).mockResolvedValue({
      success: true,
      client: {
        name: 'Wang',
        id_number: '123',
        phone: '13800000000',
        address: 'Beijing',
        legal_representative: 'Li',
        legal_representative_id_number: '456',
        client_type: 'legal',
      },
    })

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)
    const textarea = screen.getByPlaceholderText(/粘贴当事人信息文本/)
    fireEvent.change(textarea, { target: { value: 'full text' } })
    fireEvent.click(screen.getByText('解析文本'))

    await waitFor(() => {
      expect(screen.getByText('解析成功')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('确认填充'))
    expect(defaultProps.onParsed).toHaveBeenCalledWith({
      name: 'Wang',
      id_number: '123',
      phone: '13800000000',
      address: 'Beijing',
      legal_representative: 'Li',
      legal_representative_id_number: '456',
      client_type: 'legal',
    })
  })

  it('does nothing when handleApply called with no result', () => {
    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)
    // No result set => onParsed should not be called
    expect(defaultProps.onParsed).not.toHaveBeenCalled()
  })

  it('recognizes image with legal_representative data', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: true,
      extracted_data: { name: 'Corp', legal_representative: 'Boss' },
    })

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'biz.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('解析成功')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('确认填充'))
    expect(defaultProps.onParsed).toHaveBeenCalledWith({ name: 'Corp', legal_representative: 'Boss' })
  })

  it('calls onParsed with partial result from recognition', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: true,
      extracted_data: { id_number: '12345' },
    })

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'id.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('解析成功')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('确认填充'))
    expect(defaultProps.onParsed).toHaveBeenCalledWith({ id_number: '12345' })
  })

  it('disables parse button during loading', async () => {
    vi.mocked(clientApi.parseText).mockImplementation(() => new Promise(() => {}))

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)
    const textarea = screen.getByPlaceholderText(/粘贴当事人信息文本/)
    fireEvent.change(textarea, { target: { value: 'text' } })
    fireEvent.click(screen.getByText('解析文本'))

    await waitFor(() => {
      const parseBtn = screen.getByText('解析文本')
      expect(parseBtn).toBeDisabled()
    })
  })
})
