vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...p }: Record<string, unknown>) => <div {...p}>{children}</div>,
  CardContent: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  CardHeader: ({ children }: Record<string, unknown>) => <div>{children}</div>,
  CardTitle: ({ children }: Record<string, unknown>) => <h3>{children}</h3>,
}))

vi.mock('@/components/shared/DropZone', () => ({
  DropZone: ({ onClick, ariaLabel }: { onClick: () => void; ariaLabel: string }) => (
    <div data-testid="drop-zone" role="button" aria-label={ariaLabel} onClick={onClick} />
  ),
}))

vi.mock('@/lib/file-utils', () => ({
  isPdf: vi.fn((file: File) => file.name.endsWith('.pdf')),
  formatFileSize: vi.fn((size: number) => `${(size / 1024).toFixed(0)} KB`),
  MAX_FILE_SIZE_10MB: 10 * 1024 * 1024,
}))

vi.mock('lucide-react', () => {
  const Icon = (p: Record<string, unknown>) => <svg data-testid="icon" {...p} />
  return {
    FileImage: Icon, FileText: Icon, Loader2: Icon, CheckCircle2: Icon,
    XCircle: Icon, X: Icon, AlertCircle: Icon,
  }
})

vi.mock('../../api', () => ({
  clientApi: {
    recognizeIdentityDoc: vi.fn(),
    submitRecognizeTask: vi.fn(),
    getRecognizeTaskStatus: vi.fn(),
  },
}))

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { OcrUploader } from '../OcrUploader'
import { clientApi } from '../../api'

describe('OcrUploader', () => {
  const defaultProps = {
    onRecognized: vi.fn(),
    onError: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the OCR title', () => {
    render(<OcrUploader {...defaultProps} />)
    expect(screen.getByText('OCR 智能识别')).toBeInTheDocument()
  })

  it('renders the drop zone', () => {
    render(<OcrUploader {...defaultProps} />)
    expect(screen.getByTestId('drop-zone')).toBeInTheDocument()
  })

  it('renders hint text', () => {
    render(<OcrUploader {...defaultProps} />)
    expect(screen.getByText(/上传身份证或营业执照图片/)).toBeInTheDocument()
  })

  it('renders async mode toggle', () => {
    render(<OcrUploader {...defaultProps} />)
    expect(screen.getByText('异步模式')).toBeInTheDocument()
  })

  it('calls recognizeIdentityDoc when a file is selected', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: true,
      doc_type: 'id_card',
      extracted_data: { name: 'Wang', id_number: '110101199001011234' },
      confidence: 0.95,
    })

    render(<OcrUploader {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(clientApi.recognizeIdentityDoc).toHaveBeenCalledWith(file)
    })
  })

  it('calls onError when file type is invalid', async () => {
    render(<OcrUploader {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.txt', { type: 'text/plain' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(defaultProps.onError).toHaveBeenCalledWith(expect.stringContaining('不支持的文件格式'))
    })
  })

  it('shows recognition result when OCR succeeds', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: true,
      doc_type: 'id_card',
      extracted_data: { name: 'Wang', id_number: '110101199001011234', address: 'Beijing' },
      confidence: 0.95,
    })

    render(<OcrUploader {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('识别成功')).toBeInTheDocument()
      expect(screen.getByText('Wang')).toBeInTheDocument()
      expect(screen.getByText('110101199001011234')).toBeInTheDocument()
    })
  })

  it('calls onRecognized when confirm button is clicked', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: true,
      doc_type: 'id_card',
      extracted_data: { name: 'Wang', id_number: '110101199001011234' },
      confidence: 0.95,
    })

    render(<OcrUploader {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('确认填充')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('确认填充'))
    expect(defaultProps.onRecognized).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Wang', id_number: '110101199001011234' }),
    )
  })

  it('shows error when OCR fails', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: false,
      doc_type: '',
      extracted_data: {},
      confidence: 0,
      error: 'OCR failed',
    })

    render(<OcrUploader {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(defaultProps.onError).toHaveBeenCalledWith('OCR failed')
    })
  })
})
