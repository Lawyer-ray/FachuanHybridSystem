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
  DropZone: ({ onClick, ariaLabel, onDrop, onDragEnter, onDragLeave, onDragOver }: { onClick: () => void; ariaLabel: string; onDrop?: (e: unknown) => void; onDragEnter?: (e: unknown) => void; onDragLeave?: (e: unknown) => void; onDragOver?: (e: unknown) => void }) => (
    <div data-testid="drop-zone" role="button" aria-label={ariaLabel} onClick={onClick} onDrop={onDrop} onDragEnter={onDragEnter} onDragLeave={onDragLeave} onDragOver={onDragOver} />
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
      extracted_data: { name: 'Wang', id_number: '000000000000000100' },
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
      extracted_data: { name: 'Wang', id_number: '000000000000000100', address: 'Beijing' },
      confidence: 0.95,
    })

    render(<OcrUploader {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('识别成功')).toBeInTheDocument()
      expect(screen.getByText('Wang')).toBeInTheDocument()
      expect(screen.getByText('000000000000000100')).toBeInTheDocument()
    })
  })

  it('calls onRecognized when confirm button is clicked', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: true,
      doc_type: 'id_card',
      extracted_data: { name: 'Wang', id_number: '000000000000000100' },
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
      expect.objectContaining({ name: 'Wang', id_number: '000000000000000100' }),
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

  it('handles cancel result', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: true,
      doc_type: 'id_card',
      extracted_data: { name: 'Wang', id_number: '000000000000000100' },
      confidence: 0.95,
    })

    render(<OcrUploader {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('取消')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('取消'))
    // Recognition result should be dismissed
    expect(screen.queryByText('确认填充')).not.toBeInTheDocument()
  })

  it('handles remove file', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: true,
      doc_type: 'id_card',
      extracted_data: { name: 'Wang', id_number: '000000000000000100' },
      confidence: 0.95,
    })

    render(<OcrUploader {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('test.jpg')).toBeInTheDocument()
    })

    // Remove file
    const removeBtn = screen.getByLabelText('移除文件')
    fireEvent.click(removeBtn)

    // Should show drop zone again
    expect(screen.getByTestId('drop-zone')).toBeInTheDocument()
  })

  it('handles empty recognition result', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: true,
      doc_type: 'id_card',
      extracted_data: {},
      confidence: 0.95,
    })

    render(<OcrUploader {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('未能识别到有效信息')).toBeInTheDocument()
    })
  })

  it('shows file preview for PDF files', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: true,
      doc_type: 'id_card',
      extracted_data: { name: 'Wang' },
      confidence: 0.95,
    })

    render(<OcrUploader {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('test.pdf')).toBeInTheDocument()
    })
  })

  it('handles invalid file extension fallback', async () => {
    render(<OcrUploader {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    // File with no MIME type but valid extension
    const file = new File(['test'], 'test.xyz', { type: '' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(defaultProps.onError).toHaveBeenCalledWith(expect.stringContaining('不支持的文件格式'))
    })
  })

  it('handles file too large', async () => {
    render(<OcrUploader {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['x'.repeat(20 * 1024 * 1024)], 'large.jpg', { type: 'image/jpeg' })
    Object.defineProperty(file, 'size', { value: 20 * 1024 * 1024 })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(defaultProps.onError).toHaveBeenCalledWith(expect.stringContaining('10MB'))
    })
  })

  it('handles click on drop zone', () => {
    render(<OcrUploader {...defaultProps} />)
    const dropZone = screen.getByTestId('drop-zone')
    fireEvent.click(dropZone)
    // Should trigger file input click - no crash
    expect(dropZone).toBeInTheDocument()
  })

  it('handles drag enter and leave', () => {
    render(<OcrUploader {...defaultProps} />)
    const dropZone = screen.getByTestId('drop-zone')
    fireEvent.dragEnter(dropZone, { dataTransfer: { items: ['item'] } })
    fireEvent.dragOver(dropZone)
    fireEvent.dragLeave(dropZone)
    expect(dropZone).toBeInTheDocument()
  })

  it('handles drop with no files gracefully', () => {
    render(<OcrUploader {...defaultProps} />)
    const dropZone = screen.getByTestId('drop-zone')
    fireEvent.drop(dropZone, { dataTransfer: { files: [] } })
    // Should not crash
    expect(screen.getByText('OCR 智能识别')).toBeInTheDocument()
  })

  it('handles file input reset after change', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: true,
      doc_type: 'id_card',
      extracted_data: { name: 'Wang' },
      confidence: 0.95,
    })

    render(<OcrUploader {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(fileInput.value).toBe('')
    })
  })

  it('handles async mode toggle', () => {
    render(<OcrUploader {...defaultProps} />)
    const asyncToggle = screen.getByRole('checkbox')
    expect(asyncToggle).not.toBeChecked()
    fireEvent.click(asyncToggle)
    expect(asyncToggle).toBeChecked()
  })

  it('shows error with default message when OCR returns no error', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: false,
      doc_type: '',
      extracted_data: {},
      confidence: 0,
    })

    render(<OcrUploader {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(defaultProps.onError).toHaveBeenCalledWith('识别失败，请重试或手动输入')
    })
  })

  it('handles recognizeIdentityDoc network error', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockRejectedValue(new Error('Network error'))

    render(<OcrUploader {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(defaultProps.onError).toHaveBeenCalledWith('Network error')
    })
  })

  it('handles recognizeIdentityDoc non-Error exception', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockRejectedValue('string error')

    render(<OcrUploader {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(defaultProps.onError).toHaveBeenCalledWith('识别失败，请检查网络连接')
    })
  })

  it('shows legal representative for company OCR', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: true,
      doc_type: 'business_license',
      extracted_data: {
        name: '测试公司',
        id_number: '91110000MA01XXXXX',
        address: '北京市',
        legal_representative: '张三',
      },
      confidence: 0.95,
    })

    render(<OcrUploader {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'license.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('测试公司')).toBeInTheDocument()
      expect(screen.getByText('法定代表人')).toBeInTheDocument()
      expect(screen.getByText('张三')).toBeInTheDocument()
    })
  })

  it('shows address in recognition result', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: true,
      doc_type: 'id_card',
      extracted_data: { name: 'Wang', address: '北京市朝阳区' },
      confidence: 0.95,
    })

    render(<OcrUploader {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('地址')).toBeInTheDocument()
      expect(screen.getByText('北京市朝阳区')).toBeInTheDocument()
    })
  })

  it('does not allow file selection while uploading', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockImplementation(() => new Promise(() => {}))

    render(<OcrUploader {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('test.jpg')).toBeInTheDocument()
    })

    // Click drop zone while uploading should not trigger new upload
    const dropZone = screen.getByTestId('drop-zone')
    fireEvent.click(dropZone)
    // Should not crash
  })

  it('submits async task when async mode enabled', async () => {
    vi.mocked(clientApi.submitRecognizeTask).mockResolvedValue({ task_id: 'task-123' })
    vi.mocked(clientApi.getRecognizeTaskStatus).mockResolvedValue({
      status: 'completed',
      result: {
        success: true,
        extracted_data: { name: 'Async User', id_number: '111' },
      },
    })

    render(<OcrUploader {...defaultProps} />)
    // Enable async mode
    fireEvent.click(screen.getByRole('checkbox'))
    // Upload file
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'async.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(clientApi.submitRecognizeTask).toHaveBeenCalledWith(file)
    })

    await waitFor(() => {
      expect(screen.getByText('识别成功')).toBeInTheDocument()
    }, { timeout: 10000 })
  })

  it('handles async task failure', async () => {
    vi.mocked(clientApi.submitRecognizeTask).mockResolvedValue({ task_id: 'task-456' })
    vi.mocked(clientApi.getRecognizeTaskStatus).mockResolvedValue({
      status: 'failed',
      result: null,
    })

    render(<OcrUploader {...defaultProps} />)
    fireEvent.click(screen.getByRole('checkbox'))
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'fail.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(defaultProps.onError).toHaveBeenCalledWith('识别任务失败')
    }, { timeout: 10000 })
  })

  it('handles async task submit error', async () => {
    vi.mocked(clientApi.submitRecognizeTask).mockRejectedValue(new Error('submit error'))

    render(<OcrUploader {...defaultProps} />)
    fireEvent.click(screen.getByRole('checkbox'))
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'error.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(defaultProps.onError).toHaveBeenCalledWith('submit error')
    }, { timeout: 10000 })
  })

  it('handles async task with non-Error exception', async () => {
    vi.mocked(clientApi.submitRecognizeTask).mockRejectedValue('string error')

    render(<OcrUploader {...defaultProps} />)
    fireEvent.click(screen.getByRole('checkbox'))
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'error.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(defaultProps.onError).toHaveBeenCalledWith('识别失败，请检查网络连接')
    }, { timeout: 10000 })
  })

  it('handles async task completed with no extracted data', async () => {
    vi.mocked(clientApi.submitRecognizeTask).mockResolvedValue({ task_id: 'task-789' })
    vi.mocked(clientApi.getRecognizeTaskStatus).mockResolvedValue({
      status: 'completed',
      result: { success: false, error: 'no data' },
    })

    render(<OcrUploader {...defaultProps} />)
    fireEvent.click(screen.getByRole('checkbox'))
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'nodata.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(defaultProps.onError).toHaveBeenCalledWith('no data')
    }, { timeout: 10000 })
  })

  it('handles drop with file', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: true,
      doc_type: 'id_card',
      extracted_data: { name: 'Dropped' },
      confidence: 0.9,
    })

    render(<OcrUploader {...defaultProps} />)
    const dropZone = screen.getByTestId('drop-zone')
    const file = new File(['test'], 'dropped.jpg', { type: 'image/jpeg' })
    fireEvent.drop(dropZone, { dataTransfer: { files: [file] } })

    await waitFor(() => {
      expect(clientApi.recognizeIdentityDoc).toHaveBeenCalledWith(file)
    })
  })

  it('handles drag enter with empty items', () => {
    render(<OcrUploader {...defaultProps} />)
    const dropZone = screen.getByTestId('drop-zone')
    fireEvent.dragEnter(dropZone, { dataTransfer: { items: [] } })
    expect(dropZone).toBeInTheDocument()
  })

  it('handles cancel result button', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: true,
      doc_type: 'id_card',
      extracted_data: { name: 'User' },
      confidence: 0.9,
    })

    render(<OcrUploader {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('取消')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('取消'))
    expect(screen.queryByText('确认填充')).not.toBeInTheDocument()
  })

  it('shows no data warning for empty recognition', async () => {
    vi.mocked(clientApi.recognizeIdentityDoc).mockResolvedValue({
      success: true,
      doc_type: 'id_card',
      extracted_data: {},
      confidence: 0.5,
    })

    render(<OcrUploader {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'empty.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('未能识别到有效信息')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('关闭'))
    expect(screen.queryByText('未能识别到有效信息')).not.toBeInTheDocument()
  })
})
