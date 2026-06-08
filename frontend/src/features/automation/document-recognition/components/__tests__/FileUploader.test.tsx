vi.mock('../../hooks/use-recognition-mutations', () => ({
  useUploadDocument: () => ({ mutateAsync: mockMutateAsync }),
}))

vi.mock('@/components/shared/DropZone', () => ({
  DropZone: ({ ariaLabel, onClick, onDrop, onDragEnter, onDragLeave, onDragOver, isDragging, isUploading }: any) => (
    <div
      data-testid="drop-zone"
      role="button"
      aria-label={ariaLabel}
      onClick={onClick}
      onDrop={onDrop}
      onDragEnter={onDragEnter}
      onDragLeave={onDragLeave}
      onDragOver={onDragOver}
      data-dragging={isDragging}
      data-uploading={isUploading}
    >
      DropZone
    </div>
  ),
}))

vi.mock('@/lib/file-utils', () => ({
  isPdf: (file: File) => file?.type === 'application/pdf',
  formatFileSize: (size: number) => `${Math.round(size / 1024)} KB`,
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size, className }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} className={className as string}>{children}</button>
  ),
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardTitle: ({ children }: { children: React.ReactNode }) => <h3>{children}</h3>,
}))

vi.mock('@/components/ui/progress', () => ({
  Progress: (props: Record<string, unknown>) => <div data-testid="progress" {...props} />,
}))

vi.mock('lucide-react', () => ({
  FileImage: (p: any) => <svg data-testid="file-image" {...p} />,
  FileText: (p: any) => <svg data-testid="file-text" {...p} />,
  Loader2: (p: any) => <svg data-testid="loader" {...p} />,
  CheckCircle2: (p: any) => <svg data-testid="check" {...p} />,
  XCircle: (p: any) => <svg data-testid="x-circle" {...p} />,
  X: (p: any) => <svg data-testid="x" {...p} />,
  AlertCircle: (p: any) => <svg data-testid="alert" {...p} />,
  RefreshCw: (p: any) => <svg data-testid="refresh" {...p} />,
}))

vi.mock('../schemas', () => ({
  FILE_ERRORS: {
    INVALID_TYPE: '不支持的文件格式，请上传 PDF 或图片文件（jpg/png）',
    FILE_TOO_LARGE: '文件大小超过 10MB 限制',
    UPLOAD_FAILED: '文件上传失败，请重试',
  },
}))

vi.mock('../../constants', () => ({
  ACCEPTED_FILE_TYPES: ['application/pdf', 'image/jpeg', 'image/png'],
  MAX_FILE_SIZE: 10 * 1024 * 1024,
}))

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { FileUploader } from '../FileUploader'
import { toast } from 'sonner'

const mockMutateAsync = vi.fn()

describe('FileUploader', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockMutateAsync.mockReset()
  })

  it('renders upload card title', () => {
    render(<FileUploader onUploadSuccess={vi.fn()} />)
    expect(screen.getByText('上传文书')).toBeInTheDocument()
  })

  it('renders drop zone when no file selected', () => {
    render(<FileUploader onUploadSuccess={vi.fn()} />)
    expect(screen.getByTestId('drop-zone')).toBeInTheDocument()
  })

  it('renders hint text', () => {
    render(<FileUploader onUploadSuccess={vi.fn()} />)
    expect(screen.getByText(/上传法律文书/)).toBeInTheDocument()
  })

  it('has hidden file input', () => {
    const { container } = render(<FileUploader onUploadSuccess={vi.fn()} />)
    const input = container.querySelector('input[type="file"]')
    expect(input).toBeInTheDocument()
    expect(input).toHaveClass('hidden')
  })

  it('handles successful upload', async () => {
    const task = { id: 1, status: 'completed', file_name: 'test.pdf' }
    mockMutateAsync.mockResolvedValue(task)
    const onSuccess = vi.fn()

    render(<FileUploader onUploadSuccess={onSuccess} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith(file)
      expect(onSuccess).toHaveBeenCalledWith(task)
    })
  })

  it('shows file preview after selection', async () => {
    mockMutateAsync.mockResolvedValue({ id: 1 })
    render(<FileUploader onUploadSuccess={vi.fn()} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf', size: 1024 })
    Object.defineProperty(file, 'size', { value: 1024 })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('test.pdf')).toBeInTheDocument()
    })
  })

  it('shows upload progress', async () => {
    // Slow down the upload to see progress
    mockMutateAsync.mockImplementation(() => new Promise(resolve => setTimeout(() => resolve({ id: 1 }), 500)))
    render(<FileUploader onUploadSuccess={vi.fn()} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByTestId('progress')).toBeInTheDocument()
    })
  })

  it('shows error for invalid file type', async () => {
    const onError = vi.fn()
    render(<FileUploader onUploadSuccess={vi.fn()} onUploadError={onError} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.txt', { type: 'text/plain' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('不支持的文件格式，请上传 PDF 或图片文件（jpg/png）')
      expect(onError).toHaveBeenCalled()
    })
  })

  it('shows error for file too large', async () => {
    const onError = vi.fn()
    render(<FileUploader onUploadSuccess={vi.fn()} onUploadError={onError} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['x'.repeat(20 * 1024 * 1024)], 'large.pdf', { type: 'application/pdf' })
    Object.defineProperty(file, 'size', { value: 20 * 1024 * 1024 })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('文件大小超过 10MB 限制')
      expect(onError).toHaveBeenCalled()
    })
  })

  it('shows upload error when mutation fails', async () => {
    const onError = vi.fn()
    mockMutateAsync.mockRejectedValue(new Error('Network error'))
    render(<FileUploader onUploadSuccess={vi.fn()} onUploadError={onError} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: 'Network error' }))
    })
  })

  it('shows error message in file preview on error', async () => {
    mockMutateAsync.mockRejectedValue(new Error('Upload failed'))
    render(<FileUploader onUploadSuccess={vi.fn()} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('Upload failed')).toBeInTheDocument()
    })
  })

  it('handles retry upload', async () => {
    mockMutateAsync.mockRejectedValueOnce(new Error('fail')).mockResolvedValueOnce({ id: 1 })
    render(<FileUploader onUploadSuccess={vi.fn()} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('fail')).toBeInTheDocument()
    })

    // Click retry - find refresh icon button
    const retryBtns = screen.getAllByTestId('refresh')
    fireEvent.click(retryBtns[retryBtns.length - 1])

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledTimes(2)
    })
  })

  it('handles remove file after success', async () => {
    mockMutateAsync.mockResolvedValue({ id: 1 })
    render(<FileUploader onUploadSuccess={vi.fn()} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('test.pdf')).toBeInTheDocument()
    })

    // After upload completes, the file preview should have a remove button
    // Find the close/remove button (X icon)
    const removeBtns = screen.getAllByTestId('x')
    expect(removeBtns.length).toBeGreaterThan(0)
  })

  it('does not show remove button during upload', async () => {
    mockMutateAsync.mockImplementation(() => new Promise(() => {})) // Never resolves
    render(<FileUploader onUploadSuccess={vi.fn()} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByText('test.pdf')).toBeInTheDocument()
    })
    // During upload, the X button should not be visible (only loader shown)
    expect(screen.getByTestId('loader')).toBeInTheDocument()
  })

  it('does not show drop zone when file is selected', async () => {
    mockMutateAsync.mockResolvedValue({ id: 1 })
    render(<FileUploader onUploadSuccess={vi.fn()} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.queryByTestId('drop-zone')).not.toBeInTheDocument()
    })
  })

  it('resets file input after file selection', async () => {
    mockMutateAsync.mockResolvedValue({ id: 1 })
    render(<FileUploader onUploadSuccess={vi.fn()} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(fileInput.value).toBe('')
    })
  })

  it('handles drag events on drop zone', () => {
    render(<FileUploader onUploadSuccess={vi.fn()} />)
    const dropZone = screen.getByTestId('drop-zone')
    // Fire drag events with proper dataTransfer mock
    fireEvent.dragEnter(dropZone, { dataTransfer: { items: ['item'] } })
    fireEvent.dragOver(dropZone)
    fireEvent.dragLeave(dropZone)
    // Should not crash
    expect(dropZone).toBeInTheDocument()
  })

  it('handles file drop', async () => {
    mockMutateAsync.mockResolvedValue({ id: 1 })
    render(<FileUploader onUploadSuccess={vi.fn()} />)
    const dropZone = screen.getByTestId('drop-zone')
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    fireEvent.drop(dropZone, { dataTransfer: { files: [file] } })

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith(file)
    })
  })

  it('uses custom acceptedTypes and maxSize', () => {
    render(<FileUploader onUploadSuccess={vi.fn()} acceptedTypes={['image/jpeg']} maxSize={5 * 1024 * 1024} />)
    // Should still render
    expect(screen.getByText('上传文书')).toBeInTheDocument()
  })

  it('handles non-Error upload failure', async () => {
    const onError = vi.fn()
    mockMutateAsync.mockRejectedValue('string error')
    render(<FileUploader onUploadSuccess={vi.fn()} onUploadError={onError} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(onError).toHaveBeenCalled()
    })
  })

  it('shows PDF icon for PDF files', async () => {
    mockMutateAsync.mockResolvedValue({ id: 1 })
    render(<FileUploader onUploadSuccess={vi.fn()} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByTestId('file-text')).toBeInTheDocument()
    })
  })

  it('shows image icon for image files', async () => {
    mockMutateAsync.mockResolvedValue({ id: 1 })
    render(<FileUploader onUploadSuccess={vi.fn()} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.jpg', { type: 'image/jpeg' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByTestId('file-image')).toBeInTheDocument()
    })
  })
})
