vi.mock('../../hooks/use-recognition-mutations', () => ({
  useUploadDocument: () => ({ mutateAsync: vi.fn() }),
}))

vi.mock('@/components/shared/DropZone', () => ({
  DropZone: ({ ariaLabel }: any) => <div aria-label={ariaLabel}>DropZone</div>,
}))

vi.mock('@/lib/file-utils', () => ({
  isPdf: (file: File) => file?.type === 'application/pdf',
  formatFileSize: (size: number) => `${Math.round(size / 1024)} KB`,
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { render, screen } from '@testing-library/react'
import { FileUploader } from '../FileUploader'

describe('FileUploader', () => {
  it('renders upload card title', () => {
    render(<FileUploader onUploadSuccess={vi.fn()} />)
    expect(screen.getByText('上传文书')).toBeInTheDocument()
  })

  it('renders drop zone', () => {
    render(<FileUploader onUploadSuccess={vi.fn()} />)
    expect(screen.getByText('DropZone')).toBeInTheDocument()
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
})
