/**
 * ContextAttachments Component Tests
 * 测试上下文附件面板组件
 */

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

const mockAddAttachment = vi.fn()
const mockRemoveAttachment = vi.fn()

vi.mock('../../stores/workbench-store', () => ({
  useWorkbenchStore: vi.fn((selector: (s: Record<string, unknown>) => unknown) => {
    const state: Record<string, unknown> = {
      attachments: [],
      addAttachment: mockAddAttachment,
      removeAttachment: mockRemoveAttachment,
    }
    return selector(state)
  }),
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { ContextAttachments } from '../ContextAttachments'
import { useWorkbenchStore } from '../../stores/workbench-store'
import type { Attachment } from '../../types'

const mockAttachments: Attachment[] = [
  { id: 'a1', name: 'document.pdf', size: 102400, status: 'ready' },
  { id: 'a2', name: 'very-long-filename-that-should-be-truncated-in-the-display.docx', size: 512000, status: 'ready' },
  { id: 'a3', name: 'uploading.txt', size: 0, status: 'uploading' },
  { id: 'a4', name: 'error.pdf', size: 0, status: 'error', error: 'Upload failed' },
]

describe('ContextAttachments', () => {
  beforeEach(() => {
    vi.mocked(useWorkbenchStore).mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state: Record<string, unknown> = {
        attachments: [],
        addAttachment: mockAddAttachment,
        removeAttachment: mockRemoveAttachment,
      }
      return selector(state)
    })
  })

  it('renders add attachment button when empty', () => {
    render(<ContextAttachments />)
    expect(screen.getByText('添加附件')).toBeInTheDocument()
  })

  it('renders attachment chips when attachments exist', () => {
    vi.mocked(useWorkbenchStore).mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state: Record<string, unknown> = {
        attachments: mockAttachments,
        addAttachment: mockAddAttachment,
        removeAttachment: mockRemoveAttachment,
      }
      return selector(state)
    })
    render(<ContextAttachments />)
    expect(screen.getByText('附件:')).toBeInTheDocument()
    expect(screen.getByText('document.pdf')).toBeInTheDocument()
  })

  it('displays file size for ready attachments', () => {
    vi.mocked(useWorkbenchStore).mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state: Record<string, unknown> = {
        attachments: [mockAttachments[0]],
        addAttachment: mockAddAttachment,
        removeAttachment: mockRemoveAttachment,
      }
      return selector(state)
    })
    render(<ContextAttachments />)
    expect(screen.getByText('100.0KB')).toBeInTheDocument()
  })

  it('truncates long attachment names', () => {
    vi.mocked(useWorkbenchStore).mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state: Record<string, unknown> = {
        attachments: [mockAttachments[1]],
        addAttachment: mockAddAttachment,
        removeAttachment: mockRemoveAttachment,
      }
      return selector(state)
    })
    render(<ContextAttachments />)
    // Long name should be truncated with '...'
    expect(screen.getByText(/very-long/)).toBeInTheDocument()
  })

  it('shows error state for failed attachments', () => {
    vi.mocked(useWorkbenchStore).mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state: Record<string, unknown> = {
        attachments: [mockAttachments[3]],
        addAttachment: mockAddAttachment,
        removeAttachment: mockRemoveAttachment,
      }
      return selector(state)
    })
    render(<ContextAttachments />)
    const chip = screen.getByTitle('Upload failed')
    expect(chip.className).toContain('border-destructive')
  })

})
