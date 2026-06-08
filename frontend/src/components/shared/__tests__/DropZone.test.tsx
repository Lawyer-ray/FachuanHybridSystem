import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DropZone } from '../DropZone'

const defaultProps = {
  isDragging: false,
  isUploading: false,
  onDragEnter: vi.fn(),
  onDragLeave: vi.fn(),
  onDragOver: vi.fn(),
  onDrop: vi.fn(),
  onClick: vi.fn(),
}

describe('DropZone', () => {
  it('renders default text', () => {
    render(<DropZone {...defaultProps} />)
    expect(screen.getByText('拖拽文件到此处上传')).toBeInTheDocument()
    expect(screen.getByText('或点击选择文件')).toBeInTheDocument()
  })

  it('renders custom drag text', () => {
    render(<DropZone {...defaultProps} dragText="Custom drag text" />)
    expect(screen.getByText('Custom drag text')).toBeInTheDocument()
  })

  it('shows drag state text when dragging', () => {
    render(<DropZone {...defaultProps} isDragging />)
    expect(screen.getByText('松开鼠标上传文件')).toBeInTheDocument()
  })

  it('shows uploading state', () => {
    render(<DropZone {...defaultProps} isUploading />)
    expect(screen.getByText('正在上传中...')).toBeInTheDocument()
  })

  it('renders custom uploading text', () => {
    render(<DropZone {...defaultProps} isUploading uploadingText="Uploading..." />)
    expect(screen.getByText('Uploading...')).toBeInTheDocument()
  })

  it('renders accept labels', () => {
    render(<DropZone {...defaultProps} />)
    expect(screen.getByText('PDF')).toBeInTheDocument()
    expect(screen.getByText('JPG')).toBeInTheDocument()
    expect(screen.getByText('PNG')).toBeInTheDocument()
  })

  it('renders custom accept labels', () => {
    render(<DropZone {...defaultProps} acceptLabels={['DOC', 'XLS']} />)
    expect(screen.getByText('DOC')).toBeInTheDocument()
    expect(screen.getByText('XLS')).toBeInTheDocument()
  })

  it('renders hint text', () => {
    render(<DropZone {...defaultProps} hint="Max 10MB" />)
    expect(screen.getByText('Max 10MB')).toBeInTheDocument()
  })

  it('calls onClick when clicked', async () => {
    const onClick = vi.fn()
    render(<DropZone {...defaultProps} onClick={onClick} />)
    await userEvent.click(screen.getByRole('button'))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('calls onClick on Enter key', async () => {
    const onClick = vi.fn()
    render(<DropZone {...defaultProps} onClick={onClick} />)
    const dropzone = screen.getByRole('button')
    dropzone.focus()
    await userEvent.keyboard('{Enter}')
    expect(onClick).toHaveBeenCalled()
  })

  it('has correct aria-label', () => {
    render(<DropZone {...defaultProps} ariaLabel="Upload files" />)
    expect(screen.getByLabelText('Upload files')).toBeInTheDocument()
  })
})
