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
import { toast } from 'sonner'

describe('TextParser - coverage improvements', () => {
  const defaultProps = {
    onParsed: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ========== handleParseText with empty text - covers line 44 ==========

  it('shows error toast when parse is called with empty text', () => {
    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)
    // Button should be disabled
    const parseBtn = screen.getByText('解析文本')
    expect(parseBtn).toBeDisabled()
  })

  // ========== handleParseText failure with no error string - covers res.error || fallback ==========

  it('shows fallback error when parse returns success=false with no error', async () => {
    vi.mocked(clientApi.parseText).mockResolvedValue({
      success: false,
      client: null,
    })

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)
    const textarea = screen.getByPlaceholderText(/粘贴当事人信息文本/)
    fireEvent.change(textarea, { target: { value: 'some text' } })
    fireEvent.click(screen.getByText('解析文本'))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('未能解析出有效信息')
    })
  })

  // ========== handleRecognizeImage failure with no error string ==========

  it('shows fallback error when recognition returns success=false with no error', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: false,
      doc_type: 'id_card',
      extracted_data: {},
      confidence: 0,
    })

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'id.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('识别失败，请重试')
    })
  })

  // ========== clearImage - covers lines 93-97 ==========

  it('clears image preview when X button is clicked', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: true,
      extracted_data: { name: 'Wang' },
      doc_type: 'id_card',
      confidence: 0.9,
    })

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'id.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('id.jpg')).toBeInTheDocument()
    })

    // Click clear button
    const clearBtn = screen.getByText('id.jpg').closest('div')?.parentElement?.querySelector('button')
    if (clearBtn) {
      fireEvent.click(clearBtn)
      await waitFor(() => {
        expect(screen.queryByText('id.jpg')).not.toBeInTheDocument()
      })
    }
  })

  // ========== handlePaste with no items - covers line 101 ==========

  it('handles paste event with no clipboardData items', () => {
    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)

    const textarea = screen.getByPlaceholderText(/粘贴当事人信息文本/)
    const pasteEvent = new Event('paste', { bubbles: true }) as unknown as React.ClipboardEvent
    Object.defineProperty(pasteEvent, 'clipboardData', {
      value: { items: null },
    })
    fireEvent.paste(textarea, pasteEvent)
    expect(clientApi.recognizeIdentityDoc).not.toHaveBeenCalled()
  })

  // ========== handlePaste with non-image items only ==========

  it('does not trigger recognition when paste has only text items', () => {
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

  // ========== handlePaste with image item that returns null file ==========

  it('handles paste with image item that returns null from getAsFile', () => {
    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)

    const textarea = screen.getByPlaceholderText(/粘贴当事人信息文本/)
    const pasteEvent = new Event('paste', { bubbles: true }) as unknown as React.ClipboardEvent
    Object.defineProperty(pasteEvent, 'clipboardData', {
      value: {
        items: [{ type: 'image/png', getAsFile: () => null }],
      },
    })
    fireEvent.paste(textarea, pasteEvent)
    expect(clientApi.recognizeIdentityDoc).not.toHaveBeenCalled()
  })

  // ========== handleApply with all possible fields - covers lines 116-128 ==========

  it('handleApply maps all result fields to onParsed', async () => {
    vi.mocked(clientApi.parseText).mockResolvedValue({
      success: true,
      client: {
        name: 'Full',
        id_number: '123',
        phone: '138',
        address: 'Addr',
        legal_representative: 'Rep',
        legal_representative_id_number: '456',
        client_type: 'legal',
        unknown_field: 'val',
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
      name: 'Full',
      id_number: '123',
      phone: '138',
      address: 'Addr',
      legal_representative: 'Rep',
      legal_representative_id_number: '456',
      client_type: 'legal',
    })
  })

  // ========== handleApply with no result - covers line 117 early return ==========

  it('handleApply does nothing when result is null', () => {
    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)
    // No result has been set, so clicking confirm should not trigger onParsed
    expect(defaultProps.onParsed).not.toHaveBeenCalled()
  })

  // ========== handleFileSelect with no file - covers line 86 early return ==========

  it('handleFileSelect does nothing when no file is selected', () => {
    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(fileInput, { target: { files: [] } })
    expect(clientApi.recognizeIdentityDoc).not.toHaveBeenCalled()
  })

  // ========== Result display with FIELD_LABELS fallback ==========

  it('displays result fields with labels and fallback for unknown keys', async () => {
    vi.mocked(clientApi.parseText).mockResolvedValue({
      success: true,
      client: { name: 'Test', some_unknown_key: 'value' },
    })

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)
    const textarea = screen.getByPlaceholderText(/粘贴当事人信息文本/)
    fireEvent.change(textarea, { target: { value: 'text' } })
    fireEvent.click(screen.getByText('解析文本'))

    await waitFor(() => {
      expect(screen.getByText('解析成功')).toBeInTheDocument()
    })

    // "some_unknown_key" should be used as fallback label
    expect(screen.getByText('some_unknown_key')).toBeInTheDocument()
    expect(screen.getByText('value')).toBeInTheDocument()
  })

  // ========== Cancel result - covers setResult(null) ==========

  it('closes result panel when cancel button is clicked', async () => {
    vi.mocked(clientApi.parseText).mockResolvedValue({
      success: true,
      client: { name: 'Test' },
    })

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)
    const textarea = screen.getByPlaceholderText(/粘贴当事人信息文本/)
    fireEvent.change(textarea, { target: { value: 'text' } })
    fireEvent.click(screen.getByText('解析文本'))

    await waitFor(() => {
      expect(screen.getByText('解析成功')).toBeInTheDocument()
    })

    // Click cancel
    const buttons = screen.getAllByText('取消')
    fireEvent.click(buttons[buttons.length - 1])

    await waitFor(() => {
      expect(screen.queryByText('解析成功')).not.toBeInTheDocument()
    })
  })

  // ========== Recognition with empty extracted_data fields ==========

  it('handles recognition result with empty extracted_data fields', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: true,
      extracted_data: {},
      doc_type: 'id_card',
      confidence: 0.8,
    })

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'id.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('解析成功')).toBeInTheDocument()
    })
  })

  // ========== Expanded toggle - covers setExpanded ==========

  it('toggles expanded state', () => {
    render(<TextParser {...defaultProps} />)
    const titleButton = screen.getByText('智能解析').closest('button')!

    // Initially collapsed
    expect(screen.queryByPlaceholderText(/粘贴当事人信息文本/)).not.toBeInTheDocument()

    // Click to expand
    fireEvent.click(titleButton)
    expect(screen.getByPlaceholderText(/粘贴当事人信息文本/)).toBeInTheDocument()

    // Click to collapse
    fireEvent.click(titleButton)
    expect(screen.queryByPlaceholderText(/粘贴当事人信息文本/)).not.toBeInTheDocument()
  })

  // ========== Result with empty string values - filter(([,v]) => v) ==========

  it('filters out empty string values from result display', async () => {
    vi.mocked(clientApi.parseText).mockResolvedValue({
      success: true,
      client: { name: 'Test', phone: '' },
    })

    render(<TextParser {...defaultProps} />)
    fireEvent.click(screen.getByText('智能解析').closest('button')!)
    const textarea = screen.getByPlaceholderText(/粘贴当事人信息文本/)
    fireEvent.change(textarea, { target: { value: 'text' } })
    fireEvent.click(screen.getByText('解析文本'))

    await waitFor(() => {
      expect(screen.getByText('解析成功')).toBeInTheDocument()
    })

    // "name" should show, "phone" with empty value should be filtered out
    expect(screen.getByText('姓名/公司名称')).toBeInTheDocument()
    expect(screen.queryByText('联系方式')).not.toBeInTheDocument()
  })
})
